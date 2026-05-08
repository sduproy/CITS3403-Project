"""
Database CLI helpers and startup bootstrap.

Two entry points:

  1. ``init_db()`` / ``flask init-db`` — DESTRUCTIVE: drops every table
     SQLAlchemy knows about, recreates them from the models, and
     re-seeds the default admin (admin / admin). Used to reset state.

  2. ``bootstrap_db()`` — IDEMPOTENT: creates any missing tables and
     seeds the admin only if no users exist yet. Called once at app
     startup so a fresh checkout — or a checkout where someone
     deleted ``instance/travelplan.sqlite`` — Just Works without
     having to remember ``flask init-db`` first.

Models are imported transitively via ``app.py``, so ``db.create_all()``
sees ``users``, ``itineraries``, and ``reviews``.
"""

import click
from werkzeug.security import generate_password_hash
from datetime import date

from extensions import db
from models import User, Itinerary, Day, Activity


def _seed_default_admin():
    """Insert the default admin user. Caller is responsible for ensuring
    they aren't about to violate the username UNIQUE constraint."""
    db.session.add(
        User(
            username="admin",
            email="admin@smartvoyage.local",
            password_hash=generate_password_hash("admin", method="pbkdf2:sha256"),
            role="admin",
        )
    )
    db.session.commit()

def _seed_sample_trip():
    """Insert a base intinerary"""
    db.session.add(
        Itinerary(
            user_id = 1,
            destination = "Japan",
            start_date = date(2025, 1, 1),
            end_date = date(2025, 1, 2),
        )
    )
    db.session.flush()

    db.session.add(
        Day(
            itinerary_id = 1,
            day_number = 1,

        )
    )
    db.session.add(
        Day(
            itinerary_id = 1,
            day_number = 2,
            
        )
    )
    db.session.flush()

    db.session.add_all([
        Activity(day_id=1, time="9:00AM",  title="Breakfast at Kurokatsusan", info="Famous breakfast spot.", order=0),
        Activity(day_id=1, time="11:00AM", title="Sushi making class at NOBU", info="World class course.",  order=1),
        Activity(day_id=2, time="9:00AM",  title="Flight to Kyoto",            info="Don't miss it.",       order=0),
    ])
    db.session.commit()

def init_db():
    """Destructive: drop every table, recreate the schema, seed admin."""
    db.drop_all()
    db.create_all()
    _seed_default_admin()
    _seed_sample_trip()


def bootstrap_db():
    """Idempotent: create any missing tables, seed admin only if the users
    table is completely empty.

    This is what makes ``rm instance/travelplan.sqlite && flask run`` work
    — the next request would otherwise hit "no such table: users" because
    SQLite auto-creates an empty database file but ``db.create_all()``
    is never called by the request lifecycle on its own.

    The "only if no users" guard means we never resurrect an admin that
    you intentionally deleted or renamed.
    """
    db.create_all()
    if User.query.count() == 0:
        _seed_default_admin()
        _seed_sample_trip()

@click.command("init-db")
def init_db_command():
    """Drop existing tables, recreate schema via SQLAlchemy, seed default admin."""
    init_db()
    click.echo(
        "Initialized the database. "
        "Default admin seeded (username: admin, password: admin)."
    )


def init_app(app):
    """Register the init-db CLI command on the given Flask app."""
    app.cli.add_command(init_db_command)
