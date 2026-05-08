"""
Flask extensions, instantiated without an app.

These objects are bound to the Flask app later via their ``init_app(app)``
method (see ``app.py``). Keeping them in their own module avoids circular
imports — ``models.py`` and ``app.py`` can both import ``db`` and ``login``
from here without importing each other.
"""

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Alembic-backed migration framework. Bound to the app + db in app.py
# via migrate.init_app(app, db). Once wired, ``flask db init / migrate
# / upgrade / downgrade`` become available on the CLI and start writing
# migration scripts to the migrations/ folder at repo root.
migrate = Migrate()

login = LoginManager()
# Endpoint that @login_required redirects anonymous users to. The Blueprint
# is named ``main`` (see routes.py), so the endpoint is ``main.login``.
login.login_view = "main.login"
# Match the flash category our existing templates style for errors.
login.login_message = "Please log in to access this page."
login.login_message_category = "error"
