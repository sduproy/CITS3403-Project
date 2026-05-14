import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

# Load .env (if present) before reading os.environ.get(...) below. Flask
# auto-loads .env when launched via `flask run`, but not on bare imports
# or `python app.py`; calling load_dotenv() here makes the behaviour
# consistent across every entry point.
load_dotenv()

import db
import seed_community
from extensions import db as sa_db, login, migrate
import models  # noqa: F401 — registers models with SQLAlchemy at import time
from routes import main


app = Flask(__name__, instance_relative_config=True)
Path(app.instance_path).mkdir(parents=True, exist_ok=True)

# SECRET_KEY signs the session cookie and the Flask-WTF CSRF tokens, so
# leaking it lets an attacker forge both. The security lecture is explicit:
# "secret keys ... should always be manually configured and never stored
# under version control". We read from the environment first; the fallback
# below is named loud enough to flag any deploy that forgot to set it.
# python-dotenv (in requirements.txt) means Flask auto-loads a .env file
# on startup if one is present, so local dev just needs a single line:
#   SECRET_KEY=<some-long-random-string>
db_path = Path(app.instance_path) / "travelplan.sqlite"
app.config.from_mapping(
    SECRET_KEY=os.environ.get("SECRET_KEY") or "dev-only-INSECURE-set-SECRET_KEY-env-var",
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_path}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    # Google AI Studio key for the Gemini-powered itinerary generator
    # (see gemini.py). Loaded from the environment so it stays out of
    # source control. None means /itinerary/new will refuse to call
    # the AI and flash an error instead.
    GOOGLE_API_KEY=os.environ.get("GOOGLE_API_KEY"),
)

sa_db.init_app(app)
# Migrate must be bound after SQLAlchemy and before any code that uses
# the migration history; with both wired, ``flask db migrate / upgrade
# / downgrade`` work from the CLI.
migrate.init_app(app, sa_db)
login.init_app(app)
seed_community.init_app(app)
db.init_app(app)
app.register_blueprint(main)

# Bootstrap the database the first time the app starts against an empty
# (or missing) instance/travelplan.sqlite — creates any missing tables
# and seeds the default admin if no users exist yet. Idempotent: a no-op
# on subsequent starts where the schema is already in place.
with app.app_context():
    db.bootstrap_db()


if __name__ == "__main__":
    app.run(debug=True)
