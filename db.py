"""
Database CLI helpers.

The raw sqlite3 layer that lived here was replaced by SQLAlchemy in
the security-lecture-driven refactor (Phase A). This module now only
holds the ``flask init-db`` command, which:

  1. Drops and recreates every table SQLAlchemy knows about.
  2. Seeds the default admin user (username: admin, password: admin)
     so a fresh checkout has a working admin account for local dev.

Models are imported transitively via ``app.py``, so ``db.create_all()``
sees ``users``, ``itineraries``, and ``reviews``.
"""

import click
from flask import current_app
from werkzeug.security import generate_password_hash

from extensions import db
from models import User


def init_db():
    """Drop all tables, recreate them from the SQLAlchemy models, seed admin."""
    db.drop_all()
    db.create_all()

    if User.query.filter_by(username="admin").first() is None:
        admin = User(
            username="admin",
            email="admin@smartvoyage.local",
            password_hash=generate_password_hash("admin"),
            role="admin",
        )
        db.session.add(admin)
        db.session.commit()


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
