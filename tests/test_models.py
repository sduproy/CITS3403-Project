"""
Unit tests for the SQLAlchemy models in ``models.py``.

These exercise the parts of the model layer that aren't just attribute
storage: password hashing through werkzeug, the ``Itinerary`` <-> ``User``
relationship cascade, the per-(user, itinerary) review uniqueness
constraint, and the rating-range check constraint. Each test is small,
fast, and isolated — the lecture's five properties of a good unit test.
"""

import unittest
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import Itinerary, Review, User
from tests.helpers import ALICE_PASSWORD, BaseTestCase


class UserModelTests(BaseTestCase, unittest.TestCase):
    """User: hashing, uniqueness, role default, cascades."""

    def test_seeded_user_can_check_correct_password(self):
        alice = User.query.filter_by(username="alice").first()
        self.assertIsNotNone(alice)
        self.assertTrue(check_password_hash(alice.password_hash, ALICE_PASSWORD))

    def test_seeded_user_rejects_wrong_password(self):
        alice = User.query.filter_by(username="alice").first()
        self.assertFalse(check_password_hash(alice.password_hash, "not-the-password"))

    def test_password_hash_is_not_plaintext(self):
        # Sanity: the hashing path actually runs (pbkdf2:sha256:...$salt$hex).
        alice = User.query.filter_by(username="alice").first()
        self.assertNotEqual(alice.password_hash, ALICE_PASSWORD)
        self.assertTrue(alice.password_hash.startswith("pbkdf2:"))

    def test_duplicate_username_is_rejected(self):
        db.session.add(
            User(
                username="alice",  # already taken in seed_test_data
                email="other@example.com",
                password_hash=generate_password_hash("x", method="pbkdf2:sha256"),
            )
        )
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_default_role_is_user(self):
        bob = User(
            username="bob",
            email="bob@example.com",
            password_hash=generate_password_hash("x", method="pbkdf2:sha256"),
        )
        db.session.add(bob)
        db.session.commit()
        self.assertEqual(bob.role, "user")

    def test_deleting_user_cascades_to_their_itineraries(self):
        alice = User.query.filter_by(username="alice").first()
        self.assertEqual(len(alice.itineraries), 1)
        itin_id = alice.itineraries[0].id

        db.session.delete(alice)
        db.session.commit()

        self.assertIsNone(db.session.get(Itinerary, itin_id))


class ItineraryModelTests(BaseTestCase, unittest.TestCase):
    """Itinerary: defaults, relationship, public/private flag."""

    def test_is_public_defaults_to_private(self):
        alice = User.query.filter_by(username="alice").first()
        trip = Itinerary(
            user_id=alice.id,
            destination="Tokyo, Japan",
            arrive_time=datetime(2026, 7, 1, 9, 0),
            leave_time=datetime(2026, 7, 7, 21, 0),
        )
        db.session.add(trip)
        db.session.commit()
        # Default in the model is 0 = private.
        self.assertEqual(trip.is_public, 0)
        self.assertEqual(trip.content, "")

    def test_itinerary_belongs_to_owning_user(self):
        alice = User.query.filter_by(username="alice").first()
        trip = alice.itineraries[0]
        self.assertEqual(trip.user.username, "alice")
        self.assertEqual(trip.destination, "Perth, Australia")


class ReviewModelTests(BaseTestCase, unittest.TestCase):
    """Review: unique-per-(user, itinerary), rating range."""

    def _alice_and_admin_trip(self):
        alice = User.query.filter_by(username="alice").first()
        admin = User.query.filter_by(username="admin").first()
        return alice, admin, alice.itineraries[0]

    def test_admin_can_review_alices_trip_once(self):
        _, admin, trip = self._alice_and_admin_trip()
        db.session.add(Review(itinerary_id=trip.id, user_id=admin.id, rating=4, comment="Nice"))
        db.session.commit()

        review = Review.query.filter_by(user_id=admin.id, itinerary_id=trip.id).one()
        self.assertEqual(review.rating, 4)
        self.assertEqual(review.comment, "Nice")

    def test_same_user_cannot_review_same_trip_twice(self):
        _, admin, trip = self._alice_and_admin_trip()
        db.session.add(Review(itinerary_id=trip.id, user_id=admin.id, rating=4))
        db.session.commit()

        db.session.add(Review(itinerary_id=trip.id, user_id=admin.id, rating=5))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_rating_must_be_between_1_and_5(self):
        _, admin, trip = self._alice_and_admin_trip()
        db.session.add(Review(itinerary_id=trip.id, user_id=admin.id, rating=6))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_deleting_itinerary_cascades_to_reviews(self):
        _, admin, trip = self._alice_and_admin_trip()
        db.session.add(Review(itinerary_id=trip.id, user_id=admin.id, rating=3))
        db.session.commit()
        trip_id = trip.id

        db.session.delete(trip)
        db.session.commit()

        self.assertEqual(Review.query.filter_by(itinerary_id=trip_id).count(), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
