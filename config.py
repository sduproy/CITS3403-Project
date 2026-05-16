"""
Application configuration classes.

We need multiple configurations for the same Flask app — on-disk SQLite
for normal runs, in-memory SQLite for unit and Selenium tests. The
factory method ``create_app(config_class)`` in ``app.py`` picks one at
startup; the base ``Config`` holds the settings shared between them.

This file follows the lecture pattern:

    class Config:               # shared
    class DeploymentConfig:     # real run
    class TestConfig:           # in-memory + TESTING flag

The factory then does ``app.config.from_object(config_class)``.
"""

import os
from pathlib import Path

from sqlalchemy.pool import StaticPool

# Absolute path to the project root so DeploymentConfig can build a
# DB URI that doesn't depend on the current working directory the app
# is launched from.
BASE_DIR = Path(__file__).resolve().parent


class Config:
    """Settings shared by every configuration."""

    # SECRET_KEY signs the session cookie and the Flask-WTF CSRF tokens, so
    # leaking it lets an attacker forge both. Loaded from the environment
    # first; the fallback below is named loud enough to flag any deploy
    # that forgot to set it. python-dotenv loads .env on app startup if
    # one is present, so local dev just needs a single line:
    #     SECRET_KEY=<some-long-random-string>
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-INSECURE-set-SECRET_KEY-env-var"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Google AI Studio key for the Gemini-powered itinerary generator
    # (see gemini.py). Loaded from the environment so it stays out of
    # source control. None means /itinerary/new will refuse to call
    # the AI and flash an error instead.
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

    # Pixabay key for the destination-image proxy at /api/destination_image
    # (see routes.py). Loaded from .env so it stays out of source control
    # and never reaches the browser. None means the proxy returns null
    # and the cards fall back to loremflickr.
    PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")


class DeploymentConfig(Config):
    """Normal-run config: on-disk SQLite under instance/."""

    SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(BASE_DIR / "instance" / "travelplan.sqlite")


class TestConfig(Config):
    """Config used by unit + Selenium tests.

    - ``sqlite:///:memory:`` is non-persistent: each test gets a fresh
      schema via ``db.create_all()`` / ``db.drop_all()`` in
      setUp/tearDown, satisfying the lecture's "tests should not update
      persistent state" property.
    - ``TESTING=True`` is Flask's standard test-mode switch (propagates
      exceptions to the test runner, disables error pages). It is also
      our signal to skip ``bootstrap_db()`` at app startup — tests own
      their own schema lifecycle.
    - ``WTF_CSRF_ENABLED=False`` lets the Flask test client and Selenium
      POST to form-protected routes without baking a CSRF token into
      every test.
    - ``SERVER_NAME`` lets ``url_for`` work outside a request context
      when the Selenium tests are building expected URLs.
    """

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    # Force every SQLAlchemy connection to use the SAME underlying
    # SQLite handle. Without this, the Selenium tests' background
    # server thread would open a *separate* :memory: database and not
    # see the users/itineraries seeded by the test thread. ``StaticPool``
    # holds one connection; ``check_same_thread=False`` lets multiple
    # threads share it. Harmless for unit tests (the test client
    # runs everything in one thread anyway).
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
