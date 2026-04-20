import sqlite3

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf-8"))

    existing = db.execute(
        "SELECT id FROM users WHERE username = ?", ("admin",)
    ).fetchone()
    if existing is None:
        db.execute(
            "INSERT INTO users (username, email, password_hash, role)"
            " VALUES (?, ?, ?, ?)",
            (
                "admin",
                "admin@smartvoyage.local",
                generate_password_hash("admin"),
                "admin",
            ),
        )
        db.commit()


@click.command("init-db")
def init_db_command():
    """Drop existing tables, recreate schema, and seed the default admin."""
    init_db()
    click.echo(
        "Initialized the database. "
        "Default admin seeded (username: admin, password: admin)."
    )


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
