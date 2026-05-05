"""
Application routes.

Phase B of the security refactor: Flask-Login replaces the manual
session["user_id"] / g.user mechanism. Highlights:

- ``@login_required`` is imported from ``flask_login`` (still preserves
  ``?next=`` automatically — Flask-Login redirects anonymous users to
  ``login.login_view`` with the original path appended).
- ``current_user`` (a thread-local proxy from Flask-Login) replaces
  ``g.user`` everywhere, including the templates that previously read
  ``g.user.username`` / ``g.user.role``.
- ``login_user(user)`` and ``logout_user()`` replace the manual
  ``session["user_id"] = ...`` / ``session.clear()`` calls.
- The ``admin_required`` decorator stays custom — Flask-Login doesn't
  cover role-based authorisation, only authentication. It now reads
  ``current_user`` instead of ``g.user``.
"""

import functools
from datetime import date

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from forms import LoginForm, RegisterForm
from models import Itinerary, User

main = Blueprint("main", __name__)


def admin_required(view):
    """Gate a view to users with role == 'admin'. Anon users go to login."""

    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "error")
            return redirect(url_for("main.login", next=request.path))
        if current_user.role != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("main.index"))
        return view(**kwargs)

    return wrapped_view


@main.route("/")
def index():
    return render_template("itinerary.html")


@main.route("/community")
def community():
    return render_template("community.html")


@main.route("/register", methods=("GET", "POST"))
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            db.session.add(
                User(
                    username=form.username.data,
                    email=form.email.data.lower(),
                    password_hash=generate_password_hash(form.password.data),
                )
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("That username or email is already registered.", "error")
        else:
            flash("Account created — please log in.", "success")
            return redirect(url_for("main.login"))
    elif form.is_submitted():
        # form.is_submitted() is True for any POST; we get here only if
        # validation failed (CSRF, required, length, regexp, email format).
        # Surface the first error per field as flash messages so the
        # existing alert styling at the top of base.html keeps working.
        for field_errors in form.errors.values():
            for msg in field_errors:
                flash(msg, "error")
                break  # one error per field is enough to point the user at the issue

    return render_template("register.html", form=form)


@main.route("/login", methods=("GET", "POST"))
def login():
    form = LoginForm()
    if form.validate_on_submit():
        identifier = form.username.data.strip()
        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()

        if user is None or not check_password_hash(user.password_hash, form.password.data):
            flash("Invalid username or password.", "error")
            return render_template("login.html", form=form)

        login_user(user, remember=form.remember_me.data)
        flash(f"Welcome back, {user.username}!", "success")

        # Honor ?next=<path>, but only relative paths (guard against open redirects).
        next_url = request.args.get("next", "")
        if next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)

        if user.role == "admin":
            return redirect(url_for("main.admin_dashboard"))
        return redirect(url_for("main.dashboard"))
    elif form.is_submitted():
        # POST that failed validation (CSRF or required field). Surface
        # the first error per field as a flash so base.html's alerts
        # keep rendering them.
        for field_errors in form.errors.values():
            for msg in field_errors:
                flash(msg, "error")
                break

    return render_template("login.html", form=form)


@main.route("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("main.index"))


@main.route("/dashboard")
@login_required
def dashboard():
    itineraries = (
        Itinerary.query.filter_by(user_id=current_user.id)
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
        user_id=current_user.id,
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
    itinerary = Itinerary.query.filter_by(id=id, user_id=current_user.id).first()
    if itinerary is not None:
        db.session.delete(itinerary)
        db.session.commit()
    flash("Itinerary deleted.", "success")
    return redirect(url_for("main.dashboard"))


# Route stubs to add as features land:
#   /itinerary/<int:id>      (full AI-generated itinerary detail page)
