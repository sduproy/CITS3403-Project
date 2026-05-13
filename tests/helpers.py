"""
Shared test fixtures.

``BaseTestCase`` follows the lecture's setUp / tearDown recipe:

    def setUp(self):
        testApp = create_app(TestConfig)
        self.app_context = testApp.app_context()
        self.app_context.push()
        db.create_all()
        add_test_data_to_db()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

The seed data (one regular user + one admin + one public itinerary
owned by the regular user) is small on purpose: any test that needs a
specific scenario adds its own rows on top in the test method itself.
"""

from datetime import datetime

from werkzeug.security import generate_password_hash

from app import create_app
from config import TestConfig
from extensions import db
from models import Itinerary, User


# Plain-text passwords for the seeded users so tests can log them in.
ALICE_PASSWORD = "alice-password"
ADMIN_PASSWORD = "admin-password"


def seed_test_data():
    """Insert a minimal, predictable fixture into the in-memory DB."""
    alice = User(
        username="alice",
        email="alice@example.com",
        password_hash=generate_password_hash(ALICE_PASSWORD, method="pbkdf2:sha256"),
        role="user",
    )
    admin = User(
        username="admin",
        email="admin@example.com",
        password_hash=generate_password_hash(ADMIN_PASSWORD, method="pbkdf2:sha256"),
        role="admin",
    )
    db.session.add_all([alice, admin])
    db.session.flush()  # populate primary keys before referencing them

    # One public itinerary belonging to alice. Tests that need a private
    # one (or one owned by someone else) can flip is_public or add their
    # own row.
    public_trip = Itinerary(
        user_id=alice.id,
        destination="Perth, Australia",
        arrive_time=datetime(2026, 6, 1, 10, 0),
        leave_time=datetime(2026, 6, 5, 18, 0),
        content="",
        is_public=1,
    )
    db.session.add(public_trip)
    db.session.commit()


class BaseTestCase:
    """Mixin that wires the lecture's setUp/tearDown onto a unittest.TestCase.

    Used by both the unit-test and the Selenium-test classes — keeps
    the schema-lifecycle code in exactly one place.
    """

    def setUp(self):
        self.testApp = create_app(TestConfig)
        self.app_context = self.testApp.app_context()
        self.app_context.push()
        db.create_all()
        seed_test_data()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
