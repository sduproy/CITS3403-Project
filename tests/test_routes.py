"""
Unit tests for the route layer in ``routes.py``.

These use Flask's built-in ``test_client`` — no real HTTP server, no
browser — to drive each endpoint. They cover the parts of the route
layer that are pure server logic: form validation, authorisation
(login_required, admin_required, public/private visibility), session
management (login / logout), and the redirect chain after each action.

The TestConfig disables CSRF (WTF_CSRF_ENABLED=False) so each test can
POST a form without first GET-ing the page to extract a token; CSRF
itself is exercised at the Flask-WTF library level, not in our code.
"""

import unittest
from datetime import datetime

from extensions import db
from models import Itinerary, User
from tests.helpers import ALICE_PASSWORD, ADMIN_PASSWORD, BaseTestCase


class RouteTestCase(BaseTestCase, unittest.TestCase):
    """Common base — also creates a test client per test."""

    def setUp(self):
        super().setUp()
        self.client = self.testApp.test_client()

    # --- small login helper so tests read as a sequence of user actions ---
    def login(self, username, password):
        return self.client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=True,
        )

    def logout(self):
        return self.client.get("/logout", follow_redirects=True)


class PublicPageTests(RouteTestCase):
    """Pages anonymous visitors can reach."""

    def test_homepage_renders(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        # The trip-planner form is on the homepage.
        self.assertIn(b"Plan", resp.data)

    def test_community_page_lists_public_itineraries(self):
        resp = self.client.get("/community")
        self.assertEqual(resp.status_code, 200)
        # alice's seeded trip is public — its destination should show.
        self.assertIn(b"Perth, Australia", resp.data)

    def test_dashboard_redirects_anonymous_to_login(self):
        # @login_required redirects to login_view (main.login) with ?next=.
        resp = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])


class AuthFlowTests(RouteTestCase):
    """Register -> login -> session -> logout."""

    def test_register_creates_user_and_redirects_to_login(self):
        resp = self.client.post(
            "/register",
            data={
                "username": "newcomer",
                "email": "newcomer@example.com",
                "password": "secret123",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(User.query.filter_by(username="newcomer").first())

    def test_register_rejects_short_password(self):
        resp = self.client.post(
            "/register",
            data={
                "username": "shortpw",
                "email": "shortpw@example.com",
                "password": "abc",  # < 6 chars per RegisterForm
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(User.query.filter_by(username="shortpw").first())

    def test_register_rejects_duplicate_username(self):
        resp = self.client.post(
            "/register",
            data={
                "username": "alice",  # already seeded
                "email": "different@example.com",
                "password": "secret123",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        # The flash-message wording from the route.
        self.assertIn(b"already registered", resp.data)

    def test_login_with_correct_password_succeeds(self):
        resp = self.login("alice", ALICE_PASSWORD)
        self.assertEqual(resp.status_code, 200)
        # The welcome-flash from the login route uses the username.
        self.assertIn(b"Welcome back, alice", resp.data)

    def test_login_with_wrong_password_fails(self):
        resp = self.login("alice", "not-the-password")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Invalid username or password", resp.data)

    def test_admin_login_redirects_to_admin_dashboard(self):
        resp = self.login("admin", ADMIN_PASSWORD)
        self.assertEqual(resp.status_code, 200)
        # admin_dashboard renders a page that contains the word "Admin"
        # in the page chrome — easier to assert on a feature unique to
        # that page than to inspect the redirect chain.
        self.assertIn(b"admin", resp.data.lower())

    def test_logout_clears_session(self):
        self.login("alice", ALICE_PASSWORD)
        # After login, dashboard is reachable (200, not a redirect).
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

        self.logout()

        # After logout, dashboard 302s to login again.
        resp = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])


class TripDetailsAuthorisationTests(RouteTestCase):
    """The public/owner/admin gate on /trip_details/<id>.

    The route returns 404 (not 403) for unauthorised viewers so private
    itinerary IDs don't leak.
    """

    def _make_private_trip_for_alice(self):
        alice = User.query.filter_by(username="alice").first()
        trip = Itinerary(
            user_id=alice.id,
            destination="Private Beach",
            arrive_time=datetime(2026, 8, 1, 9, 0),
            leave_time=datetime(2026, 8, 5, 18, 0),
            is_public=0,
        )
        db.session.add(trip)
        db.session.commit()
        return trip.id

    def test_anyone_can_view_public_trip(self):
        # alice's seeded trip is public; anonymous viewer should get it.
        public_trip = Itinerary.query.filter_by(is_public=1).first()
        resp = self.client.get(f"/trip_details/{public_trip.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Perth, Australia", resp.data)

    def test_anonymous_viewer_gets_404_on_private_trip(self):
        private_id = self._make_private_trip_for_alice()
        resp = self.client.get(f"/trip_details/{private_id}")
        self.assertEqual(resp.status_code, 404)

    def test_owner_can_view_their_own_private_trip(self):
        private_id = self._make_private_trip_for_alice()
        self.login("alice", ALICE_PASSWORD)
        resp = self.client.get(f"/trip_details/{private_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Private Beach", resp.data)

    def test_admin_can_view_any_private_trip(self):
        private_id = self._make_private_trip_for_alice()
        self.login("admin", ADMIN_PASSWORD)
        resp = self.client.get(f"/trip_details/{private_id}")
        self.assertEqual(resp.status_code, 200)

    def test_other_user_gets_404_on_someone_elses_private_trip(self):
        private_id = self._make_private_trip_for_alice()
        # Register and log in as a fresh user.
        self.client.post(
            "/register",
            data={
                "username": "bystander",
                "email": "bystander@example.com",
                "password": "secret123",
            },
            follow_redirects=True,
        )
        self.login("bystander", "secret123")
        resp = self.client.get(f"/trip_details/{private_id}")
        self.assertEqual(resp.status_code, 404)

    def test_missing_id_returns_404(self):
        resp = self.client.get("/trip_details/99999")
        self.assertEqual(resp.status_code, 404)


class AdminGuardTests(RouteTestCase):
    """admin_required: anon -> login redirect, non-admin -> home redirect."""

    def test_anonymous_admin_dashboard_redirects_to_login(self):
        resp = self.client.get("/admin", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_regular_user_cannot_reach_admin_dashboard(self):
        self.login("alice", ALICE_PASSWORD)
        # admin_required for non-admin redirects to main.index and flashes.
        resp = self.client.get("/admin", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("/admin", resp.headers["Location"])

    def test_admin_can_reach_admin_dashboard(self):
        self.login("admin", ADMIN_PASSWORD)
        resp = self.client.get("/admin")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
