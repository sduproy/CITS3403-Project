"""
Database CLI helpers and startup bootstrap.

Two entry points:

  1. ``init_db()`` / ``flask init-db`` — DESTRUCTIVE: drops every table
     SQLAlchemy knows about, recreates them from the models, and
     re-seeds the default admin (if ADMIN_PASSWORD is set in the env).
     Used to reset state.

  2. ``bootstrap_db()`` — IDEMPOTENT: brings the schema up to the
     current Alembic head and seeds the admin only if the users table
     is completely empty. Called once at app startup so a fresh
     checkout — or a checkout where someone deleted
     ``instance/travelplan.sqlite`` — Just Works without having to
     remember ``flask db upgrade`` first.

The schema is owned by Flask-Migrate (see ``migrations/`` at repo
root). ``bootstrap_db`` calls ``flask_migrate.upgrade()`` rather than
``db.create_all()`` so the canonical schema definition lives in the
migration scripts, and the Alembic version table stays in sync with
the application's notion of "current schema". This is what lets
``flask db migrate`` autogenerate diffs correctly going forward.

Admin credentials live in the environment (loaded from ``.env`` via
python-dotenv at app startup), never in source. See ``.env.example``
for the canonical setup; the literal "admin" / "admin" default for
the uni-project markers is declared there, not here.
"""

import os

import click
from flask_migrate import upgrade as alembic_upgrade
from werkzeug.security import generate_password_hash

from extensions import db
from models import User


def _seed_default_admin():
    """Insert the default admin user, reading credentials from the env.

    Credentials are pulled from ``ADMIN_USERNAME`` / ``ADMIN_EMAIL`` /
    ``ADMIN_PASSWORD`` (loaded from ``.env`` by ``app.py`` via
    python-dotenv). If ``ADMIN_PASSWORD`` is unset, no admin is seeded
    — the deploy is responsible for either configuring one or creating
    the first user some other way. Keeping the password out of source
    means it isn't searchable in the GitHub history.

    Caller is responsible for ensuring this isn't about to violate
    the username UNIQUE constraint (bootstrap_db guards on "users
    table is empty" before calling; init_db drops everything first).
    """
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_password:
        return
    db.session.add(
        User(
            username=os.environ.get("ADMIN_USERNAME", "admin"),
            email=os.environ.get("ADMIN_EMAIL", "admin@smartvoyage.local"),
            password_hash=generate_password_hash(admin_password, method="pbkdf2:sha256"),
            role="admin",
        )
    )
    db.session.commit()


def init_db():
    """Destructive: drop every table, recreate the schema at HEAD, seed admin.

    ``db.drop_all()`` removes the application tables but NOT the
    ``alembic_version`` table — Alembic owns that one and registers it
    outside SQLAlchemy's metadata. We drop it manually so the
    follow-up ``alembic_upgrade`` replays every migration from scratch
    instead of seeing the old version row and short-circuiting to "no
    work to do".
    """
    db.drop_all()
    with db.engine.begin() as conn:
        conn.execute(db.text("DROP TABLE IF EXISTS alembic_version"))
    alembic_upgrade()
    _seed_default_admin()


def bootstrap_db():
    """Idempotent: bring the schema to current HEAD, seed admin if empty.

    Replaces the previous ``db.create_all()`` approach. With migrations
    in play, ``flask_migrate.upgrade()`` is the canonical way to put
    the database into the schema state the application's models expect:

    - On a fresh checkout (no DB file): SQLite creates an empty file,
      Alembic runs every migration up to HEAD, all tables exist.
    - On an existing DB that's behind: Alembic runs only the missing
      migrations forward. Existing rows are preserved.
    - On an up-to-date DB: Alembic detects no work to do and exits
      cleanly. Cheap.

    The "only if no users" guard means we never resurrect an admin
    you intentionally deleted or renamed.

    The seed step is wrapped in try/except so this function stays
    callable when the models are AHEAD of the DB schema — that's the
    state ``flask db migrate`` puts us in (models contain a new column,
    DB doesn't, alembic_upgrade has nothing to apply yet because the
    migration hasn't been generated). In that case the seed query fails
    on the missing column and we just skip; the migration command
    doesn't need an admin row anyway, and the next real app start runs
    bootstrap_db again after upgrade() picks up the fresh migration.
    """
    alembic_upgrade()
    try:
        if User.query.count() == 0:
            _seed_default_admin()
    except Exception:
        db.session.rollback()


@click.command("init-db")
def init_db_command():
    """Drop existing tables, replay every migration to HEAD, seed default admin."""
    init_db()
    if os.environ.get("ADMIN_PASSWORD"):
        username = os.environ.get("ADMIN_USERNAME", "admin")
        click.echo(
            f"Initialized the database. Admin seeded (username: {username}; "
            "password is the ADMIN_PASSWORD value from your .env)."
        )
    else:
        click.echo(
            "Initialized the database. No admin seeded — set "
            "ADMIN_PASSWORD in .env and re-run if you want one."
        )


def init_app(app):
    """Register the init-db CLI command on the given Flask app."""
    app.cli.add_command(init_db_command)
