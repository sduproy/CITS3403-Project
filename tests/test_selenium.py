"""
Selenium WebDriver system tests.

These drive a real (headless) Chrome browser against an in-process
Flask server backed by the same in-memory SQLite database as the
unit-test suite. Each test exercises a complete user-facing flow:
the response we assert on is whatever the browser actually renders.

Mechanics (lecture pattern, slightly adapted for Windows):

  1. ``BaseTestCase.setUp`` builds an app from ``TestConfig``, pushes
     its app context, creates the schema, and seeds the alice + admin
     fixtures (in-memory).
  2. ``werkzeug.serving.make_server`` starts the WSGI server bound to
     127.0.0.1:5555 inside a *daemon thread*. The lecture's example
     uses ``multiprocessing.Process``, but a process can't see the
     parent's in-memory SQLite, so the seeded users would be invisible
     to the server. A thread shares memory; ``StaticPool`` on
     ``TestConfig`` shares the SQLite connection across threads.
  3. Headless Chrome opens, the test acts on the page, the test
     asserts on what's rendered.
  4. ``tearDown`` shuts the server down via the make_server handle
     (releases port 5555 for the next test), quits the browser, and
     drops the schema.

Run: python -m unittest tests.test_selenium -v

Requires Chrome (or Chromium) installed on PATH. Selenium 4.6+ auto-
downloads the matching chromedriver, so no manual driver install.
"""

import threading
import time
import unittest

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from werkzeug.serving import make_server

from tests.helpers import ADMIN_PASSWORD, ALICE_PASSWORD, BaseTestCase


SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5555
LOCAL_HOST = f"http://{SERVER_HOST}:{SERVER_PORT}"


def _chrome_available():
    """Probe for a working headless Chrome; skip the suite if missing.

    Lets the test suite still pass on machines where Chrome isn't
    installed (e.g. CI runners that haven't set it up) instead of
    failing every Selenium test with the same WebDriverException.
    """
    options = Options()
    options.add_argument("--headless=new")
    try:
        d = webdriver.Chrome(options=options)
        d.quit()
        return True
    except WebDriverException:
        return False


@unittest.skipUnless(_chrome_available(), "Chrome browser not available on this machine")
class SeleniumTests(BaseTestCase, unittest.TestCase):
    """End-to-end flows driven by a real browser."""

    def setUp(self):
        super().setUp()  # create_app(TestConfig), push context, seed alice+admin

        # Spin up the WSGI server in a daemon thread so it shares the
        # in-memory SQLite with the test's app context. Saving the
        # server object lets us shut it down cleanly in tearDown so
        # the port is free for the next test.
        self.server = make_server(SERVER_HOST, SERVER_PORT, self.testApp, threaded=True)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

        options = Options()
        options.add_argument("--headless=new")
        # Slightly defensive flags that make Chrome happy on CI-style
        # boxes (no /dev/shm, restricted sandboxing). Harmless locally.
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        self.driver = webdriver.Chrome(options=options)
        # 5 s implicit wait — pages with a tiny bit of JS settling
        # (e.g. the trip_details page) won't race the assertions.
        self.driver.implicitly_wait(5)

    def tearDown(self):
        try:
            self.driver.quit()
        finally:
            self.server.shutdown()
            self.server_thread.join(timeout=5)
        super().tearDown()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _body_text(self):
        return self.driver.find_element(By.TAG_NAME, "body").text

    def _wait_for_text(self, text, timeout=8):
        """Block until ``text`` is in body.text.

        ``driver.get`` resolves on the load event, but Flask's flash
        messages render before alice's dashboard data finishes
        streaming. Polling the body keeps the assertions race-free
        without sprinkling sleep() through every test.
        """
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: text in d.find_element(By.TAG_NAME, "body").text
            )
        except TimeoutException as e:
            raise AssertionError(
                f"Timed out waiting for {text!r} on {self.driver.current_url}. "
                f"Body was: {self._body_text()[:300]!r}"
            ) from e

    def _click(self, element):
        """Click via JS so a fixed navbar / footer can't intercept.

        Selenium's native click finds the element's centre and dispatches
        a real mouse event there. Our base.html has a fixed top navbar
        that often overlaps form buttons at viewport coordinates,
        triggering ElementClickInterceptedException. A JS .click()
        dispatches on the element itself and ignores stacking context.
        """
        self.driver.execute_script("arguments[0].click();", element)

    def _do_login(self, username, password):
        """UI login — used as the first step in tests that need a session.

        We call ``.submit()`` on the password field rather than clicking
        the submit button: the fixed navbar overlaps the button at the
        viewport coordinates Selenium tries to click, which triggers
        ElementClickInterceptedException. ``.submit()`` submits the
        form the element belongs to without needing a real click.
        """
        self.driver.get(LOCAL_HOST + "/login")
        self.driver.find_element(By.ID, "username").send_keys(username)
        pw = self.driver.find_element(By.ID, "password")
        pw.send_keys(password)
        pw.submit()
        # Wait until login resolves: either we've been redirected off
        # /login (success) or the error flash has rendered on /login
        # (failure). Checking the URL is cheaper and faster than waiting
        # for specific text on the destination page — the admin dashboard
        # in particular can take a moment to fully render under load.
        WebDriverWait(self.driver, 15).until(
            lambda d: (
                "/login" not in d.current_url
                or "Invalid username or password" in d.find_element(By.TAG_NAME, "body").text
            )
        )

    # ------------------------------------------------------------------
    # tests
    # ------------------------------------------------------------------

    def test_homepage_renders_branding_and_cta(self):
        """The hero section + Start Planning CTA appear on load."""
        self.driver.get(LOCAL_HOST + "/")
        self.assertIn("SmartVoyage", self.driver.title)
        self.assertIn("Start Planning", self._body_text())

    def test_community_page_lists_seeded_public_itinerary(self):
        """The seeded Perth trip is public — should show on /community."""
        self.driver.get(LOCAL_HOST + "/community")
        self.assertIn("Perth, Australia", self._body_text())

    def test_login_flow_lands_on_dashboard(self):
        """Logging in as alice ends on a page that names her."""
        self._do_login("alice", ALICE_PASSWORD)
        self._wait_for_text("Welcome back, alice")

    def test_login_wrong_password_shows_error(self):
        """A bad password keeps the user on /login with the error flash."""
        self._do_login("alice", "wrong-password")
        self.assertIn("/login", self.driver.current_url)
        self.assertIn("Invalid username or password", self._body_text())

    def test_register_creates_account_and_redirects_to_login(self):
        """Filling the register form lands on /login with the success flash."""
        self.driver.get(LOCAL_HOST + "/register")
        self.driver.find_element(By.ID, "username").send_keys("selenium_user")
        self.driver.find_element(By.ID, "email").send_keys("selenium@example.com")
        pw = self.driver.find_element(By.ID, "password")
        pw.send_keys("strongpw1")
        pw.submit()  # see _do_login docstring for why .submit() vs .click()

        self._wait_for_text("Account created")
        self.assertIn("/login", self.driver.current_url)

    def test_dashboard_has_persistent_plan_a_trip_button(self):
        """The Plan-a-Trip CTA stays visible on the dashboard even when the
        user already has itineraries (regression for the earlier minor-fix
        commit on vy-minor-fix)."""
        self._do_login("alice", ALICE_PASSWORD)
        self.driver.get(LOCAL_HOST + "/dashboard")
        # Alice has one seeded itinerary, so we're in the "has itineraries"
        # branch of the template — the new header CTA should still be there.
        self._wait_for_text("My Itineraries")
        self.assertIn("Plan a New Trip", self._body_text())

    def test_public_trip_is_reachable_from_community_link(self):
        """Click the community-page entry and land on the trip-details page."""
        self.driver.get(LOCAL_HOST + "/community")
        self._wait_for_text("Perth, Australia")
        # Find the first link whose href targets /trip_details/ and click it
        # via JS — the link sits below the fold on small viewports and the
        # fixed footer otherwise intercepts a native click.
        link = self.driver.find_element(By.CSS_SELECTOR, "a[href*='/trip_details/']")
        self._click(link)
        WebDriverWait(self.driver, 5).until(
            lambda d: "/trip_details/" in d.current_url
        )
        # The trip_details page does a fair bit of JS (Leaflet, geocoding)
        # after the load event, so the body text we want isn't there until
        # the destination header has actually rendered. Poll for it.
        self._wait_for_text("Perth, Australia")

    def test_admin_login_reaches_admin_dashboard(self):
        """Logging in as admin lands on /admin (per the role-based redirect)."""
        self._do_login("admin", ADMIN_PASSWORD)
        # The role-based redirect sends admin to /admin; wait for the
        # page to actually load before asserting on URL.
        WebDriverWait(self.driver, 5).until(
            lambda d: "/admin" in d.current_url
        )
        self.assertIn("/admin", self.driver.current_url)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
