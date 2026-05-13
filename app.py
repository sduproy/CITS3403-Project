"""
Application factory + module-level app instance.

The factory pattern (``create_app(config_class)``) is the lecture's
recommended structure for a testable Flask app: it lets us build
multiple app instances against different configurations (production
SQLite on disk, in-memory SQLite for unit/Selenium tests) without
duplicating wiring. ``app.py`` still exposes a module-level ``app``
so ``flask run`` and ``python app.py`` keep working unchanged.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

# Load .env (if present) before reading os.environ.get(...) below. Flask
# auto-loads .env when launched via `flask run`, but not on bare imports
# or `python app.py`; calling load_dotenv() here makes the behaviour
# consistent across every entry point.
load_dotenv()

import db as db_module
from extensions import db, login, migrate
import models  # noqa: F401 — registers models with SQLAlchemy at import time
from config import DeploymentConfig


def create_app(config_class=DeploymentConfig):
    """Build a Flask app instance bound to the given configuration class.

    All extension binding, blueprint registration, and (for real runs)
    DB bootstrapping happens *inside* this function so the same
    function can produce a fresh, isolated app for each test.

    The ``routes`` import is deliberately lazy: routes.py imports forms,
    models, and gemini at module load. Importing it at the top of this
    file works today, but the lecture flags that pattern as a circular-
    dependency risk once apps grow. Keeping the import inside the
    factory matches the lecture verbatim.
    """
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.from_object(config_class)

    # Bind extensions to *this* app instance. Each call returns
    # immediately and stores app on the extension; subsequent calls
    # with a different app are fine — that's why this pattern supports
    # multiple app instances.
    db.init_app(app)
    # Migrate must be bound after SQLAlchemy and before any code that
    # uses the migration history; with both wired, ``flask db migrate /
    # upgrade / downgrade`` work from the CLI.
    migrate.init_app(app, db)
    login.init_app(app)
    db_module.init_app(app)

    # Lazy import — see docstring above for why.
    from routes import main
    app.register_blueprint(main)

    # Bootstrap the database the first time the app starts against an
    # empty (or missing) instance/travelplan.sqlite — creates any
    # missing tables and seeds the default admin if no users exist
    # yet. Idempotent: a no-op on subsequent starts where the schema
    # is already in place. Skipped under TESTING because tests own
    # the schema lifecycle themselves (setUp does db.create_all()).
    if not app.config.get("TESTING"):
        with app.app_context():
            db_module.bootstrap_db()

    return app


# Module-level instance kept so ``flask run`` (which auto-detects an
# ``app`` global in ``app.py``) and ``python app.py`` work without any
# extra environment variables.
app = create_app(DeploymentConfig)


if __name__ == "__main__":
    app.run(debug=True)
