import sqlite3

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db

main = Blueprint("main", __name__)


@main.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            "SELECT id, username, email, role FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


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
                return redirect(url_for("main.login"))

        flash(error, "error")

    return render_template("register.html")


@main.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        identifier = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not identifier or not password:
            flash("Please enter your username/email and password.", "error")
            return render_template("login.html")

        user = get_db().execute(
            "SELECT id, username, password_hash, role FROM users"
            " WHERE username = ? OR email = ?",
            (identifier, identifier.lower()),
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.", "error")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user["id"]
        flash(f"Welcome back, {user['username']}!", "success")
        return redirect(url_for("main.index"))

    return render_template("login.html")


@main.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("main.index"))


# Route stubs to add as features land:
#   /dashboard                               (M4 — user's saved itineraries)
#   /admin                                   (M5 — admin dashboard)
#   /itinerary/new, /itinerary/<int:id>      (AI generation + detail page)
