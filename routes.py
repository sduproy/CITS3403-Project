import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from db import get_db

main = Blueprint("main", __name__)


@main.route("/")
def index():
    return render_template("itinerary.html")


@main.route("/community")
def community():
    return render_template("Popular.html")


@main.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        error = None
        if not username or len(username) < 3 or len(username) > 30:
            error = "Username must be between 3 and 30 characters."
        elif not username.replace("_", "").isalnum():
            error = "Username may only contain letters, numbers, and underscores."
        elif not email or "@" not in email:
            error = "A valid email is required."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."

        if error is None:
            conn = get_db()
            try:
                conn.execute(
                    "INSERT INTO users (username, email, password_hash)"
                    " VALUES (?, ?, ?)",
                    (username, email, generate_password_hash(password)),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                error = "That username or email is already registered."
            else:
                flash("Account created — please log in.", "success")
                return redirect(url_for("main.index"))

        flash(error, "error")

    return render_template("register.html")


# Route stubs to add as features land:
#   /login, /logout                          (M3)
#   /dashboard                               (M4 — user's saved itineraries)
#   /admin                                   (M5 — admin dashboard)
#   /itinerary/new, /itinerary/<int:id>      (AI generation + detail page)
