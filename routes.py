"""
Application routes.

Authentication is delegated to Flask-Login: ``current_user`` is the
logged-in User (or AnonymousUserMixin), ``login_user`` / ``logout_user``
manage the session cookie, and ``@login_required`` (imported from
``flask_login``) gates protected endpoints and redirects anonymous
requests to ``login.login_view`` with ``?next=<path>`` preserved.

``admin_required`` below is custom — Flask-Login covers authentication
only, not role-based authorisation, so the role check is ours. Every
POST endpoint uses a Flask-WTF form whose ``form.validate_on_submit()``
gate also enforces a CSRF token before the handler runs.
"""

import functools

from flask import (
    Blueprint,
    abort,
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
from forms import DeleteItineraryForm, LoginForm, NewItineraryForm, RegisterForm
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
    # The trip-planner form on the homepage POSTs to /itinerary/new; pass
    # a NewItineraryForm here so {{ form.hidden_tag() }} can render the
    # CSRF token bound to the user's session cookie.
    return render_template("itinerary.html", form=NewItineraryForm())


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
    # One DeleteItineraryForm shared across the loop in dashboard.html so
    # every delete button gets a CSRF token via {{ delete_form.hidden_tag() }}.
    return render_template(
        "dashboard.html",
        itineraries=itineraries,
        delete_form=DeleteItineraryForm(),
    )


@main.route("/admin")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")


# This is basically the /itinerary but something else is named that rn
@main.route("/trip_details/<int:id>")
@login_required
def trip_details(id):
    itinerary = db.session.get(Itinerary, id)
    # Authorisation: must belong to the current user. Without this check
    # any logged-in user could view any other user's itinerary by guessing
    # the integer ID. ``abort(404)`` (rather than 403) refuses to confirm
    # whether the itinerary exists at all, which doesn't leak the ID space.
    if itinerary is None or itinerary.user_id != current_user.id:
        abort(404)
    return render_template("trip_details.html", itinerary=itinerary)


@main.route("/itinerary/new", methods=["POST"])
@login_required
def new_itinerary():
    form = NewItineraryForm()
    if form.validate_on_submit():
        # WTForms' DateTimeLocalField has already parsed the
        # "YYYY-MM-DDTHH:MM" strings into datetime instances. The
        # cross-field "leave > arrive" rule is enforced by
        # NewItineraryForm.validate_leave_time.
        itinerary = Itinerary(
            user_id=current_user.id,
            destination=form.destination.data.strip(),
            arrive_time=form.arrive_time.data,
            leave_time=form.leave_time.data,
            content="",
        )
        db.session.add(itinerary)
        db.session.commit()
        return redirect(url_for("main.trip_details", id=itinerary.id))

    # Validation failed (CSRF, required, or leave_time <= arrive_time).
    # Surface the first error per field as a flash and bounce back to the
    # homepage where the form lives.
    for field_errors in form.errors.values():
        for msg in field_errors:
            flash(msg, "error")
            break
    return redirect(url_for("main.index"))


@main.route("/itinerary/<int:id>/delete", methods=["POST"])
@login_required
def delete_itinerary(id):
    form = DeleteItineraryForm()
    if not form.validate_on_submit():
        # CSRF token missing or wrong — refuse the delete.
        flash("The CSRF token is missing.", "error")
        return redirect(url_for("main.dashboard"))

    itinerary = Itinerary.query.filter_by(id=id, user_id=current_user.id).first()
    if itinerary is not None:
        db.session.delete(itinerary)
        db.session.commit()
    flash("Itinerary deleted.", "success")
    return redirect(url_for("main.dashboard"))


# Route stubs to add as features land:
#   /itinerary/<int:id>      (full AI-generated itinerary detail page)
