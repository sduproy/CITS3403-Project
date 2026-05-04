"""
Application routes.

Phase A of the security refactor: queries that previously used the raw
sqlite3 cursor (g.db.execute("SELECT ...?")) now go through the
SQLAlchemy ORM. The session/auth flow is otherwise unchanged from M1-M5
plus Sakindu's itinerary save/view/delete additions; Phase B will
replace the manual session handling with Flask-Login.
"""

import functools
from datetime import date

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
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import Itinerary, User

main = Blueprint("main", __name__)


def login_required(view):
    """Redirect anonymous users to the login page, preserving the target URL."""

    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("Please log in to access this page.", "error")
            return redirect(url_for("main.login", next=request.path))
        return view(**kwargs)

    return wrapped_view


def admin_required(view):
    """Gate a view to users with role == 'admin'. Anon users get sent to login."""

    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("Please log in to access this page.", "error")
            return redirect(url_for("main.login", next=request.path))
        if g.user.role != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("main.index"))
        return view(**kwargs)

    return wrapped_view


@main.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None if user_id is None else db.session.get(User, user_id)


@main.route("/")
def index():
    return render_template("itinerary.html")


@main.route("/community")
def community():
    return render_template("community.html")


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
            try:
                db.session.add(
                    User(
                        username=username,
                        email=email,
                        password_hash=generate_password_hash(password),
                    )
                )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
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

        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()

        if user is None or not check_password_hash(user.password_hash, password):
            flash("Invalid username or password.", "error")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user.id
        flash(f"Welcome back, {user.username}!", "success")

        # Honor ?next=<path>, but only relative paths (guard against open redirects).
        next_url = request.args.get("next", "")
        if next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)

        if user.role == "admin":
            return redirect(url_for("main.admin_dashboard"))
        return redirect(url_for("main.dashboard"))

    return render_template("login.html")


@main.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("main.index"))


@main.route("/dashboard")
@login_required
def dashboard():
    itineraries = (
        Itinerary.query.filter_by(user_id=g.user.id)
        .order_by(Itinerary.created_at.desc())
        .all()
    )
    return render_template("dashboard.html", itineraries=itineraries)


@main.route("/admin")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")


# This is basically the /itinerary but something else is named that rn
@main.route("/trip_details/<int:id>")
def trip_details(id):
    itinerary = db.session.get(Itinerary, id)
    return render_template("trip_details.html", itinerary=itinerary)


@main.route("/itinerary/new", methods=["POST"])
@login_required
def new_itinerary():
    destination = request.form.get("destination", "").strip()
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()

    error = None
    if not destination:
        error = "Please enter a destination."
    elif not start_date or not end_date:
        error = "Please select start and end dates."
    elif end_date < start_date:
        error = "End date must be after start date."

    if error:
        flash(error, "error")
        return redirect(url_for("main.index"))

    # Convert ISO date strings (YYYY-MM-DD from <input type="date">) to date
    # objects so SQLAlchemy's Date column accepts them.
    itinerary = Itinerary(
        user_id=g.user.id,
        destination=destination,
        start_date=date.fromisoformat(start_date),
        end_date=date.fromisoformat(end_date),
        content="",
    )
    db.session.add(itinerary)
    db.session.commit()
    return redirect(url_for("main.trip_details", id=itinerary.id))


@main.route("/itinerary/<int:id>/delete", methods=["POST"])
@login_required
def delete_itinerary(id):
    itinerary = Itinerary.query.filter_by(id=id, user_id=g.user.id).first()
    if itinerary is not None:
        db.session.delete(itinerary)
        db.session.commit()
    flash("Itinerary deleted.", "success")
    return redirect(url_for("main.dashboard"))


# Route stubs to add as features land:
#   /itinerary/<int:id>      (full AI-generated itinerary detail page)
