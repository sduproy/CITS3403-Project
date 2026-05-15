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

import json
import unittest
from datetime import datetime, timedelta

from extensions import db
from models import Itinerary, Review, User
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


class TripDurationLimitTests(RouteTestCase):
    """forms.NewItineraryForm rejects trips longer than MAX_TRIP_DURATION
    (25 days). Driven through the /itinerary/new POST so we exercise the
    full form + route path, not just the validator in isolation.
    """

    def _trip_form(self, days):
        """Build a date/time form payload spanning ``days`` calendar days."""
        arrive = datetime(2026, 6, 1, 10, 0)
        leave = arrive + timedelta(days=days)
        return {
            "destination": "Tokyo, Japan",
            "arrive_date": arrive.strftime("%Y-%m-%d"),
            "arrive_at": arrive.strftime("%H:%M"),
            "leave_date": leave.strftime("%Y-%m-%d"),
            "leave_at": leave.strftime("%H:%M"),
        }

    def test_26_day_trip_is_rejected(self):
        """One day over the cap surfaces the duration error and stays the
        user on the homepage (no Itinerary row created)."""
        self.login("alice", ALICE_PASSWORD)
        before = Itinerary.query.count()
        resp = self.client.post(
            "/itinerary/new",
            data=self._trip_form(days=26),
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        # The flash carries the "25 days" message from forms.py.
        self.assertIn(b"within 25 days", resp.data)
        # No row was created.
        self.assertEqual(Itinerary.query.count(), before)

    def test_leave_before_arrive_is_rejected(self):
        """Same path also covers the leave-before-arrive cross-field check."""
        self.login("alice", ALICE_PASSWORD)
        data = self._trip_form(days=3)
        # Swap the dates so leave is before arrive.
        data["leave_date"], data["arrive_date"] = data["arrive_date"], data["leave_date"]
        resp = self.client.post(
            "/itinerary/new", data=data, follow_redirects=True
        )
        self.assertIn(b"Leave date/time must be after arrive", resp.data)


class DeleteItineraryTests(RouteTestCase):
    """Delete is owner-only and now returns JSON (used to redirect) so the
    dashboard can handle removal client-side without a full reload."""

    def test_owner_can_delete_their_own_itinerary(self):
        alice = User.query.filter_by(username="alice").first()
        trip = alice.itineraries[0]
        trip_id = trip.id

        self.login("alice", ALICE_PASSWORD)
        resp = self.client.post(f"/itinerary/{trip_id}/delete")

        self.assertEqual(resp.status_code, 200)
        # The route returns {"success": true} — the dashboard JS reads this.
        self.assertEqual(resp.get_json(), {"success": True})
        # Row is actually gone.
        self.assertIsNone(db.session.get(Itinerary, trip_id))

    def test_anonymous_user_cannot_delete(self):
        """No session -> @login_required bounces to /login, itinerary survives."""
        trip = User.query.filter_by(username="alice").first().itineraries[0]
        trip_id = trip.id

        resp = self.client.post(f"/itinerary/{trip_id}/delete",
                                follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        self.assertIsNotNone(db.session.get(Itinerary, trip_id))

    def test_non_owner_delete_is_silent_noop(self):
        """Admin (or any non-owner) POSTing to alice's delete route should
        NOT delete the row — the route filters by user_id=current_user.id,
        so the query returns None and the commit is skipped."""
        trip = User.query.filter_by(username="alice").first().itineraries[0]
        trip_id = trip.id

        self.login("admin", ADMIN_PASSWORD)  # admin is not the owner
        resp = self.client.post(f"/itinerary/{trip_id}/delete")

        # Route still returns "success" JSON (it doesn't know the row wasn't
        # the user's), but the row survives.
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(db.session.get(Itinerary, trip_id))


class TogglePublicTests(RouteTestCase):
    """The public/private flip used by the dashboard toggle button."""

    def test_owner_can_toggle_public_to_private(self):
        alice = User.query.filter_by(username="alice").first()
        trip = alice.itineraries[0]
        self.assertEqual(trip.is_public, 1)  # seeded as public

        self.login("alice", ALICE_PASSWORD)
        resp = self.client.post(f"/itinerary/{trip.id}/toggle_public")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"is_public": 0})
        # Verify DB-side flip.
        db.session.refresh(trip)
        self.assertEqual(trip.is_public, 0)

    def test_toggle_round_trips_back_to_public(self):
        """Two toggles should land back on the original state."""
        alice = User.query.filter_by(username="alice").first()
        trip = alice.itineraries[0]
        trip_id = trip.id

        self.login("alice", ALICE_PASSWORD)
        self.client.post(f"/itinerary/{trip_id}/toggle_public")  # -> private
        resp = self.client.post(f"/itinerary/{trip_id}/toggle_public")  # -> public

        self.assertEqual(resp.get_json(), {"is_public": 1})


class ReviewSubmissionTests(RouteTestCase):
    """POST /itinerary/<id>/review — Story 4: self-review prevention + upsert.

    Setup gives alice a public trip in the seed, so admin (a different
    user) is the reviewer in these tests.
    """

    def _alice_public_trip_id(self):
        return User.query.filter_by(username="alice").first().itineraries[0].id

    def test_admin_can_review_alices_public_trip(self):
        trip_id = self._alice_public_trip_id()
        self.login("admin", ADMIN_PASSWORD)
        resp = self.client.post(
            f"/itinerary/{trip_id}/review",
            data={"rating": 5, "comment": "Loved it"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)

        admin = User.query.filter_by(username="admin").first()
        review = Review.query.filter_by(
            itinerary_id=trip_id, user_id=admin.id
        ).one()
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, "Loved it")

    def test_alice_cannot_review_her_own_trip(self):
        """Server-side self-review block: even if the UI is bypassed, the
        route rejects a review where itinerary.user_id == current_user.id."""
        trip_id = self._alice_public_trip_id()
        self.login("alice", ALICE_PASSWORD)
        resp = self.client.post(
            f"/itinerary/{trip_id}/review",
            data={"rating": 5, "comment": "Best trip ever"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        # Jinja HTML-escapes the apostrophe in "can't" to &#39;, so we match
        # on the unambiguous prefix that doesn't contain a quote.
        self.assertIn(b"review your own itinerary", resp.data)
        # No Review row was created.
        self.assertEqual(Review.query.filter_by(itinerary_id=trip_id).count(), 0)

    def test_second_submission_updates_existing_review(self):
        """Upsert: the unique (itinerary_id, user_id) constraint means the
        route must update on resubmit, not insert a duplicate."""
        trip_id = self._alice_public_trip_id()
        admin = User.query.filter_by(username="admin").first()
        self.login("admin", ADMIN_PASSWORD)

        self.client.post(
            f"/itinerary/{trip_id}/review",
            data={"rating": 3, "comment": "Was ok"},
        )
        self.client.post(
            f"/itinerary/{trip_id}/review",
            data={"rating": 5, "comment": "Loved it on rewatch"},
        )

        reviews = Review.query.filter_by(itinerary_id=trip_id, user_id=admin.id).all()
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].rating, 5)
        self.assertEqual(reviews[0].comment, "Loved it on rewatch")

    def test_rating_below_one_is_rejected(self):
        trip_id = self._alice_public_trip_id()
        self.login("admin", ADMIN_PASSWORD)
        self.client.post(
            f"/itinerary/{trip_id}/review",
            data={"rating": 0, "comment": "Bad"},
        )
        self.assertEqual(Review.query.filter_by(itinerary_id=trip_id).count(), 0)

    def test_rating_above_five_is_rejected(self):
        trip_id = self._alice_public_trip_id()
        self.login("admin", ADMIN_PASSWORD)
        self.client.post(
            f"/itinerary/{trip_id}/review",
            data={"rating": 7, "comment": "Too good"},
        )
        self.assertEqual(Review.query.filter_by(itinerary_id=trip_id).count(), 0)

    def test_anonymous_user_redirected_to_login(self):
        """No @login -> /login redirect with the typical ?next= query."""
        trip_id = self._alice_public_trip_id()
        resp = self.client.post(
            f"/itinerary/{trip_id}/review",
            data={"rating": 4},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_cannot_review_private_itinerary(self):
        """Private itineraries don't appear on /community, so reviewing
        them isn't a supported flow — the route bounces with a flash."""
        # Flip alice's seeded trip to private.
        alice = User.query.filter_by(username="alice").first()
        trip = alice.itineraries[0]
        trip.is_public = 0
        db.session.commit()

        self.login("admin", ADMIN_PASSWORD)
        resp = self.client.post(
            f"/itinerary/{trip.id}/review",
            data={"rating": 4, "comment": "x"},
            follow_redirects=True,
        )
        self.assertIn(b"Itinerary not found", resp.data)
        self.assertEqual(Review.query.filter_by(itinerary_id=trip.id).count(), 0)


class TrendingApiTests(RouteTestCase):
    """/api/trending: top public destinations (max 5), counted across rows."""

    def _add_public_trip(self, destination, user):
        db.session.add(Itinerary(
            user_id=user.id,
            destination=destination,
            arrive_time=datetime(2026, 6, 1, 10, 0),
            leave_time=datetime(2026, 6, 5, 18, 0),
            content="",
            is_public=1,
        ))

    def _add_private_trip(self, destination, user):
        db.session.add(Itinerary(
            user_id=user.id,
            destination=destination,
            arrive_time=datetime(2026, 6, 1, 10, 0),
            leave_time=datetime(2026, 6, 5, 18, 0),
            content="",
            is_public=0,
        ))

    def test_endpoint_returns_trending_key_with_list(self):
        resp = self.client.get("/api/trending")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("trending", data)
        self.assertIsInstance(data["trending"], list)

    def test_counts_duplicate_destinations(self):
        """Three public Bali itineraries -> Bali count == 3, after .title()
        normalisation so 'bali' and 'BALI' collapse together."""
        alice = User.query.filter_by(username="alice").first()
        admin = User.query.filter_by(username="admin").first()
        self._add_public_trip("Bali, Indonesia", alice)
        self._add_public_trip("bali, indonesia", admin)
        self._add_public_trip("BALI, INDONESIA", alice)
        db.session.commit()

        resp = self.client.get("/api/trending")
        trending = {item["destination"]: item["count"]
                    for item in resp.get_json()["trending"]}
        self.assertEqual(trending.get("Bali, Indonesia"), 3)

    def test_private_itineraries_are_excluded(self):
        alice = User.query.filter_by(username="alice").first()
        # 5 private Tokyo trips should still leave Tokyo out of trending
        # (only the public Perth seed should appear).
        for _ in range(5):
            self._add_private_trip("Tokyo, Japan", alice)
        db.session.commit()

        resp = self.client.get("/api/trending")
        destinations = [item["destination"]
                        for item in resp.get_json()["trending"]]
        self.assertNotIn("Tokyo, Japan", destinations)

    def test_limited_to_five_entries(self):
        """Even with 7 distinct public destinations, only the top 5 ship."""
        alice = User.query.filter_by(username="alice").first()
        for dest in ["Rome", "Paris", "Madrid", "Berlin", "Lisbon", "Athens"]:
            self._add_public_trip(dest, alice)
        db.session.commit()

        resp = self.client.get("/api/trending")
        self.assertLessEqual(len(resp.get_json()["trending"]), 5)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
