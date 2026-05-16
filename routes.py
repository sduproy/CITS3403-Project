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
import json
from datetime import datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    jsonify,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

import gemini
import requests
from extensions import db
from forms import AdminDeleteItineraryForm, DeleteItineraryForm, DeleteUserForm, LoginForm, NewItineraryForm, RegisterForm, TogglePublicForm, ReviewForm, ManualItineraryForm, EditItineraryForm, AdminDeleteReviewForm

from models import Itinerary, User, Review

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


# How many public itineraries to show per page on /community. Kept small
# so the AJAX pagination buttons are actually exercised against the
# seed data set (which is only ~8 items at the moment).
COMMUNITY_PER_PAGE = 6


def _build_review_data(itineraries):
    """Aggregate review stats per itinerary for the community card UI.

    Returns a dict keyed by itinerary id with ``avg``/``count`` plus the
    current user's own review (if any) so the rating modal can prefill.
    Extracted from the inline loop in /community so the JSON pagination
    endpoint can reuse the exact same logic — keeps the two views
    consistent.
    """
    review_data = {}
    for itin in itineraries:
        reviews = Review.query.filter_by(itinerary_id=itin.id).all()
        avg = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else 0
        user_review = None
        if current_user.is_authenticated:
            user_review = Review.query.filter_by(itinerary_id=itin.id, user_id=current_user.id).first()
        review_data[itin.id] = {"avg": avg, "count": len(reviews), "user_review": user_review}
    return review_data


@main.route("/community")
def community():
    # Server-renders the first (requested) page so the user sees content
    # before any JavaScript runs. The pagination buttons themselves then
    # switch pages via fetch() against /api/community — see the JS at the
    # bottom of community.html.
    page = request.args.get("page", 1, type=int)
    pagination = (
        Itinerary.query.filter_by(is_public=1)
        .order_by(Itinerary.created_at.desc())
        .paginate(page=page, per_page=COMMUNITY_PER_PAGE, error_out=False)
    )
    itineraries = pagination.items
    review_data = _build_review_data(itineraries)
    return render_template(
        "community.html",
        itineraries=itineraries,
        review_data=review_data,
        review_form=ReviewForm(),
        pagination=pagination,
    )


@main.route("/api/community")
def api_community():
    """Paginated JSON feed of public itineraries.

    Powers the client-side pagination on /community: clicking a page
    number (or "Next") fires fetch('/api/community?page=N'), the browser
    rebuilds the card grid from this payload, and the URL bar is updated
    via history.pushState — no full page reload, which is the part Flask
    alone can't deliver.
    """
    page = request.args.get("page", 1, type=int)
    pagination = (
        Itinerary.query.filter_by(is_public=1)
        .order_by(Itinerary.created_at.desc())
        .paginate(page=page, per_page=COMMUNITY_PER_PAGE, error_out=False)
    )
    review_data = _build_review_data(pagination.items)

    items = []
    for itin in pagination.items:
        rd = review_data[itin.id]
        user_review = rd["user_review"]
        items.append({
            "id": itin.id,
            "destination": itin.destination,
            "user_id": itin.user_id,
            "username": itin.user.username,
            "user_initial": itin.user.username[0].upper(),
            "created_at_iso": itin.created_at.strftime("%Y-%m-%d"),
            "created_at_display": itin.created_at.strftime("%B %Y"),
            "arrive_display": itin.arrive_time.strftime("%d %b"),
            "leave_display": itin.leave_time.strftime("%d %b %Y"),
            "review": {
                "avg": rd["avg"],
                "count": rd["count"],
                "user_rating": user_review.rating if user_review else None,
                "user_comment": user_review.comment if user_review else None,
            },
            # Server is the source of truth for "can this user review this
            # itinerary?" — the JS just renders the button when this is True.
            "can_review": current_user.is_authenticated and itin.user_id != current_user.id,
            "trip_url": url_for("main.trip_details", id=itin.id),
            "profile_url": url_for("main.user_profile", username=itin.user.username),
            "review_url": url_for("main.submit_review", id=itin.id),
        })

    return jsonify({
        "page": pagination.page,
        "total_pages": pagination.pages,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
        "next_num": pagination.next_num,
        "prev_num": pagination.prev_num,
        "itineraries": items,
    })


@main.route("/register", methods=("GET", "POST"))
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            db.session.add(
                User(
                    username=form.username.data,
                    email=form.email.data.lower(),
                    password_hash=generate_password_hash(form.password.data, method="pbkdf2:sha256"),
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

        # Stamp the login timestamp before issuing the session so the
        # admin dashboard can show "last seen at ..." for any user who
        # has signed in since this column was added (migration 0002).
        user.last_login = datetime.utcnow()
        db.session.commit()

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
        toggle_form=TogglePublicForm(),
    )


@main.route("/admin")
@admin_required
def admin_dashboard():
    itineraries = Itinerary.query.order_by(Itinerary.created_at.desc()).all()
    users = User.query.filter(User.role != "admin").order_by(User.created_at.desc()).all()
    total_users = len(users)
    total_itineraries = Itinerary.query.count()
    public_itineraries = Itinerary.query.filter_by(is_public=1).count()
    private_itineraries = total_itineraries - public_itineraries

    from collections import Counter
    destinations = [i.destination.strip().title() for i in itineraries]
    top_destination = Counter(destinations).most_common(1)[0][0] if destinations else "N/A"
    reviews = Review.query.order_by(Review.created_at.desc()).all()
    
    return render_template(
        "admin_dashboard.html", 
        itineraries=itineraries,
        users=users,
        delete_itinerary_form=AdminDeleteItineraryForm(),
        delete_user_form=DeleteUserForm(),
        reviews=reviews,
        delete_review_form=AdminDeleteReviewForm(),
        total_users=total_users,
        total_itineraries=total_itineraries,
        public_itineraries=public_itineraries,
        private_itineraries=private_itineraries,
        top_destination=top_destination,
    )


@main.route("/trip_details/<int:id>")
def trip_details(id):
    itinerary = db.session.get(Itinerary, id)
    if itinerary is None:
        abort(404)

    # Authorisation: visible if the itinerary is public, OR the viewer is
    # the owner, OR the viewer is an admin. Anonymous visitors can see
    # public itineraries only. ``abort(404)`` (rather than 403) refuses
    # to confirm whether a private itinerary exists, so the ID space
    # doesn't leak to anonymous probes.
    is_owner = current_user.is_authenticated and itinerary.user_id == current_user.id
    is_admin = current_user.is_authenticated and current_user.role == "admin"
    if not (itinerary.is_public or is_owner or is_admin):
        abort(404)

    # Parse the JSON blob produced by gemini.py back into a dict for the
    # template. Older rows (pre-AI) may have empty content — render with
    # plan=None and let the template fall back to a "not yet generated"
    # state.
    plan = None
    if itinerary.content:
        try:
            plan = json.loads(itinerary.content)
        except json.JSONDecodeError:
            plan = None
    return render_template("trip_details.html", itinerary=itinerary, plan=plan)


@main.route("/itinerary/new", methods=["POST"])
@login_required
def new_itinerary():
    form = NewItineraryForm()
    if form.validate_on_submit():
        # The form has 4 fields (date + time-of-day for both arrive and
        # leave) so the native HTML5 controls auto-close and fit in one
        # row. Combine each pair into a full datetime here. The
        # cross-field "leave > arrive" rule is enforced as a datetime
        # comparison in NewItineraryForm.validate_leave_at.
        destination = form.destination.data.strip()
        arrive_time = datetime.combine(form.arrive_date.data, form.arrive_at.data)
        leave_time = datetime.combine(form.leave_date.data, form.leave_at.data)

        # Hand off to Gemini. Network call ~5-15s; user sees the redirect
        # only once the JSON is back and validated. Any failure
        # (missing API key / network / malformed response) raises
        # GeminiError, which we turn into a flash + bounce back to /.
        try:
            plan = gemini.generate_itinerary(destination, arrive_time, leave_time)
        except gemini.GeminiError as e:
            flash(e.user_message, "error")
            return redirect(url_for("main.index"))

        # Persist only on success — never save a half-baked itinerary.
        itinerary = Itinerary(
            user_id=current_user.id,
            destination=destination,
            arrive_time=arrive_time,
            leave_time=leave_time,
            content=plan.model_dump_json(),
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
        return jsonify({'error': 'CSRF token missing'}), 400

    itinerary = Itinerary.query.filter_by(id=id, user_id=current_user.id).first()
    if itinerary is not None:
        db.session.delete(itinerary)
        db.session.commit()
    flash("Itinerary deleted.", "success")
    return jsonify({'success': True})

#toggling itineraries to public and private
@main.route("/itinerary/<int:id>/toggle_public", methods=["POST"])
@login_required
def toggle_public(id):
    form = TogglePublicForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'CSRF token missing'}), 400
    itinerary = Itinerary.query.filter_by(id=id, user_id=current_user.id).first()
    if itinerary is None:
        return jsonify({'error': 'Not found'}), 404
    itinerary.is_public = 0 if itinerary.is_public else 1
    db.session.commit()
    return jsonify({'is_public': itinerary.is_public})

#admin access to deleting itineraries
@main.route("/admin/itinerary/<int:id>/delete", methods=["POST"])
@admin_required
def admin_delete_itinerary(id):
    form = AdminDeleteItineraryForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'CSRF token missing'}), 400
    itinerary = db.session.get(Itinerary, id)
    if itinerary is not None:
        db.session.delete(itinerary)
        db.session.commit()
        flash("Itinerary deleted.", "success")
    return jsonify({'success': True})

#admin access to deleting user accounts
@main.route("/admin/user/<int:id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(id):
    form = DeleteUserForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'CSRF token missing'}), 400
    user = db.session.get(User, id)
    if user is not None:
        if user.role == "admin":
            return jsonify({'error': 'Cannot delete an admin account'}), 403
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.username} deleted.", "success")
    return jsonify({'success': True})

#admin access for deleting reviews
@main.route("/admin/review/<int:id>/delete", methods=["POST"])
@admin_required
def admin_delete_review(id):
    form = AdminDeleteReviewForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'CSRF token missing'}), 400
    review = db.session.get(Review, id)
    if review is not None:
        db.session.delete(review)
        db.session.commit()
        flash("Review deleted.", "success")
    return jsonify({'success': True})


@main.route("/manual_itinerary", methods=["GET", "POST"])
@login_required
def manual_itinerary():
    form = ManualItineraryForm()
    if form.validate_on_submit():
        destination = request.form.get("destination", "").strip()
        try:
            arrive_time = datetime.strptime(
                request.form.get("arrive_date") + " " + request.form.get("arrive_at"), "%Y-%m-%d %H:%M"
            )
            leave_time = datetime.strptime(
                request.form.get("leave_date") + " " + request.form.get("leave_at"), "%Y-%m-%d %H:%M"
            )
        except (ValueError, TypeError):
            flash("Invalid date or time format.", "error")
            return redirect(url_for("main.manual_itinerary"))
        is_public = int(request.form.get("is_public", 0))
        plan_json = request.form.get("plan_json", "")
        try:
            parsed = json.loads(plan_json)
            if not isinstance(parsed.get('days'), list) or len(parsed['days']) == 0:
                raise ValueError("No days")
        except (json.JSONDecodeError, ValueError, AttributeError):
            flash("Invalid itinerary data.", "error")
            return redirect(url_for("main.manual_itinerary"))

        if leave_time <= arrive_time:
            flash("Leave date/time must be after arrive date/time.", "error")
            return redirect(url_for("main.manual_itinerary"))

        itinerary = Itinerary(
            user_id=current_user.id,
            destination=destination,
            arrive_time=arrive_time,
            leave_time=leave_time,
            content=plan_json,
            is_public=is_public,
        )
        db.session.add(itinerary)
        db.session.commit()
        return redirect(url_for("main.trip_details", id=itinerary.id))

    return render_template("manual_itinerary.html", form=form)

@main.route("/user/<username>")
def user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    itineraries = Itinerary.query.filter_by(user_id=user.id, is_public=1).order_by(Itinerary.created_at.desc()).all()
    return render_template("user_profiles.html", profile_user=user, itineraries=itineraries)


@main.route("/itinerary/<int:id>/json")
@login_required
def itinerary_json(id):
    itinerary = db.session.get(Itinerary, id)
    if itinerary is None:
        abort(404)
    is_owner = itinerary.user_id == current_user.id
    if not is_owner and current_user.role != "admin":
        abort(404)
    else:
        return jsonify({
            'destination': itinerary.destination,
            'is_public': itinerary.is_public,
            'arrive_time': itinerary.arrive_time.strftime('%Y-%m-%d %H:%M'),
            'leave_time': itinerary.leave_time.strftime('%Y-%m-%d %H:%M'),
            'content':json.loads(itinerary.content) if itinerary.content else None

        })



@main.route("/itinerary/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_itinerary(id):
    form = EditItineraryForm()
    itinerary = db.session.get(Itinerary, id)
    if itinerary is None:
        abort(404)
    is_owner = itinerary.user_id == current_user.id
    if not is_owner:
        abort(404)

    if form.validate_on_submit():
        destination = request.form.get("destination", "").strip()
        try:
            arrive_time = datetime.strptime(
                request.form.get("arrive_date") + " " + request.form.get("arrive_at"), "%Y-%m-%d %H:%M"
            )
            leave_time = datetime.strptime(
                request.form.get("leave_date") + " " + request.form.get("leave_at"), "%Y-%m-%d %H:%M"
            )
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid date or time format.'}), 400
        is_public = int(request.form.get("is_public", 0))
        plan_json = request.form.get("plan_json", "")
        try:
            parsed = json.loads(plan_json)
            if not isinstance(parsed.get('days'), list) or len(parsed['days']) == 0:
                raise ValueError("No days")
        except (json.JSONDecodeError, ValueError, AttributeError):
            return jsonify({'error': 'Invalid itinerary data.'}), 400

        if leave_time <= arrive_time:
            return jsonify({'error': 'Leave date/time must be after arrive date/time.'}), 400

        itinerary.destination=destination
        itinerary.arrive_time=arrive_time
        itinerary.leave_time=leave_time
        itinerary.content=plan_json
        itinerary.is_public=is_public
        
        db.session.commit()
        return jsonify({'success': True})
    return render_template("edit_itinerary.html", form=form, itinerary=itinerary)


@main.route("/api/trending")
def api_trending():
    """Top public destinations as JSON, for AJAX-driven client-side rendering
    of the trending chips on the community page. Returns at most 5 entries."""
    from collections import Counter
    itineraries = Itinerary.query.filter_by(is_public=1).all()
    destinations = [i.destination.strip().title() for i in itineraries]
    top = Counter(destinations).most_common(5)
    return jsonify({
        "trending": [{"destination": dest, "count": cnt} for dest, cnt in top]
    })

# Story 4: review submission with self-review prevention.
@main.route("/itinerary/<int:id>/review", methods=["POST"])
@login_required
def submit_review(id):
    form = ReviewForm()
    itinerary = db.session.get(Itinerary, id)
    if itinerary is None or not itinerary.is_public:
        flash("Itinerary not found.", "error")
        return redirect(url_for("main.community"))
    # Story 4 core: a user can't review their own itinerary — keeps
    # ratings fair. Enforced server-side so a forged POST bypassing
    # the UI gate is still rejected.
    if itinerary.user_id == current_user.id:
        flash("You can't review your own itinerary.", "error")
        return redirect(url_for("main.community"))
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for msg in field_errors:
                flash(msg, "error")
                break
        return redirect(url_for("main.community"))
    # Upsert: one review per (itinerary, user) pair (DB-enforced by the
    # UniqueConstraint on the Review model). If the user has already
    # reviewed, update; otherwise insert.
    existing = Review.query.filter_by(itinerary_id=id, user_id=current_user.id).first()
    if existing:
        existing.rating = form.rating.data
        existing.comment = form.comment.data
        flash("Your review was updated.", "success")
    else:
        db.session.add(Review(
            itinerary_id=id,
            user_id=current_user.id,
            rating=form.rating.data,
            comment=form.comment.data,
        ))
        flash("Review submitted!", "success")
    db.session.commit()
    return redirect(url_for("main.community"))

# In-memory cache so we don't burn through Pixabay's 5000/day quota
# re-fetching the same destinations every page load. Cleared on
# server restart, which is fine.
_pixabay_cache = {}


@main.route("/api/destination_image")
def destination_image():
    """Proxy to Pixabay so the API key stays server-side (never reaches
    the browser). Returns {"url": "..."} or {"url": null} if no hit."""
    destination = request.args.get("q", "").strip()
    if not destination:
        return jsonify({"url": None})

    if destination in _pixabay_cache:
        return jsonify({"url": _pixabay_cache[destination]})

    api_key = current_app.config.get("PIXABAY_API_KEY")
    if not api_key:
        return jsonify({"url": None})

    try:
        resp = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": api_key,
                "q": destination,
                "image_type": "photo",
                "category": "travel",
                "per_page": 3,
                "safesearch": "true",
            },
            timeout=5,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        url = hits[0].get("webformatURL") if hits else None
    except Exception:
        url = None

    _pixabay_cache[destination] = url
    return jsonify({"url": url})
