"""
Unit tests for the bootstrap/seed helpers in ``db.py``.

These guard a real class of regression: someone re-hardcoding the admin
password into source. The seed must read every credential from the
environment, refuse to insert anything if ADMIN_PASSWORD is unset, and
never store the password in plaintext.

These tests deliberately do NOT use ``tests.helpers.BaseTestCase`` —
``BaseTestCase`` seeds its own ``admin`` user, which would either clash
with this one (UNIQUE violation) or mask whether ``_seed_default_admin``
actually did the insert. We bring up the schema ourselves and call
``_seed_default_admin`` directly.
"""

import os
import re
import unittest
from unittest.mock import patch

from werkzeug.security import check_password_hash

import db as db_module
from app import create_app
from config import TestConfig
from db import _seed_default_admin
from extensions import db
from models import User


class SeedDefaultAdminTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_no_admin_seeded_when_password_unset(self):
        """ADMIN_PASSWORD missing → no admin row inserted, no exception."""
        # patch.dict with clear=False then explicit pop ensures we only
        # affect ADMIN_PASSWORD; other env vars (SECRET_KEY etc) stay put.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ADMIN_PASSWORD", None)
            _seed_default_admin()
        self.assertEqual(User.query.filter_by(role="admin").count(), 0)

    def test_admin_seeded_with_env_credentials(self):
        """ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD are used verbatim."""
        with patch.dict(os.environ, {
            "ADMIN_USERNAME": "envadmin",
            "ADMIN_EMAIL": "env@example.com",
            "ADMIN_PASSWORD": "very-secret-123",
        }):
            _seed_default_admin()

        admin = User.query.filter_by(username="envadmin").first()
        self.assertIsNotNone(admin, "ADMIN_PASSWORD set but no admin row created")
        self.assertEqual(admin.email, "env@example.com")
        self.assertEqual(admin.role, "admin")
        self.assertTrue(
            check_password_hash(admin.password_hash, "very-secret-123"),
            "Seeded admin's password hash didn't verify against ADMIN_PASSWORD",
        )

    def test_password_is_hashed_not_plaintext(self):
        """Sanity: pbkdf2 hashing actually runs."""
        with patch.dict(os.environ, {"ADMIN_PASSWORD": "very-secret-123"}):
            _seed_default_admin()
        admin = User.query.filter_by(role="admin").first()
        self.assertIsNotNone(admin)
        self.assertNotEqual(admin.password_hash, "very-secret-123")
        self.assertTrue(admin.password_hash.startswith("pbkdf2:"))

    def test_username_and_email_default_when_only_password_set(self):
        """Setting just ADMIN_PASSWORD falls back to sensible username/email."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("ADMIN_USERNAME", "ADMIN_EMAIL")}
        env["ADMIN_PASSWORD"] = "pw"
        with patch.dict(os.environ, env, clear=True):
            _seed_default_admin()
        admin = User.query.filter_by(role="admin").first()
        self.assertEqual(admin.username, "admin")
        self.assertEqual(admin.email, "admin@smartvoyage.local")

    def test_no_admin_password_literal_in_db_module(self):
        """Regression guard: no plaintext password literal feeding the
        password_hash() call in db.py. Read it from ADMIN_PASSWORD instead.

        Matches the previous-bug pattern
        ``generate_password_hash("anything", ...)`` and the equivalent with
        single quotes. The legitimate pattern is to pass a variable.
        """
        import inspect
        source = inspect.getsource(db_module)
        hits = re.findall(
            r'generate_password_hash\(\s*["\'][^"\']+["\']',
            source,
        )
        self.assertEqual(
            hits, [],
            f"Found a plaintext password literal in db.py: {hits!r}. "
            "Read the password from the ADMIN_PASSWORD env var instead.",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
