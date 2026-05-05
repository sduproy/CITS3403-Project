"""
SQLAlchemy ORM models — the source of truth for the database schema.

``flask init-db`` and ``bootstrap_db()`` (in db.py) build the SQLite
schema from these classes via ``db.create_all()``. Routes query them
through the ORM (``User.query.filter_by(...)``), which auto-escapes
parameters and so avoids the SQL-injection-style attacks the Flask
security lecture flags.

The ``User`` class also inherits from ``UserMixin`` so Flask-Login can
use it directly: it gets ``is_authenticated``, ``is_active``,
``is_anonymous``, and ``get_id()`` for free, and the
``@login.user_loader`` at the bottom of this file rehydrates a User
instance from the ID stored in the session cookie on each request.
"""

from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship

from extensions import db, login


class User(UserMixin, db.Model):
    """A registered SmartVoyage user (regular or admin)."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.Text, unique=True, nullable=False)
    email = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.Text, nullable=False, default="user")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # CHECK(role IN ('user', 'admin')) — keeps the schema-level guarantee.
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
    )

    # Deleting a user cascades to their itineraries and reviews.
    itineraries = relationship(
        "Itinerary",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    reviews = relationship(
        "Review",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self):  # pragma: no cover — debug only
        return f"<User {self.id} {self.username!r} role={self.role}>"


class Itinerary(db.Model):
    """A user-saved trip itinerary."""

    __tablename__ = "itineraries"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    destination = db.Column(db.Text, nullable=False)
    # Local datetimes — the moment the traveller arrives at and the moment
    # they leave the destination. The AI uses the time-of-day to avoid
    # planning activities before arrival or after departure.
    arrive_time = db.Column(db.DateTime, nullable=False)
    leave_time = db.Column(db.DateTime, nullable=False)
    # Free-form text field; the AI feature stores a JSON-serialised
    # day-by-day plan here (see gemma.py).
    content = db.Column(db.Text, nullable=False, default="")
    is_public = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="itineraries")
    reviews = relationship(
        "Review",
        back_populates="itinerary",
        cascade="all, delete-orphan",
    )

    def __repr__(self):  # pragma: no cover
        return f"<Itinerary {self.id} {self.destination!r} user={self.user_id}>"


class Review(db.Model):
    """One review per (itinerary, user) pair, rated 1-5."""

    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    itinerary_id = db.Column(
        db.Integer,
        db.ForeignKey("itineraries.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    itinerary = relationship("Itinerary", back_populates="reviews")
    user = relationship("User", back_populates="reviews")

    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating"),
        UniqueConstraint("itinerary_id", "user_id", name="uq_reviews_itinerary_user"),
    )

    def __repr__(self):  # pragma: no cover
        return f"<Review {self.id} itin={self.itinerary_id} user={self.user_id} rating={self.rating}>"


@login.user_loader
def load_user(user_id):
    """Rehydrate the user model from the ID stored in the session cookie.

    Flask-Login serialises ``user.get_id()`` (a string) into the cookie on
    login_user(...), then calls this loader on each request to turn it
    back into a User instance. Returning None signals "no such user" and
    Flask-Login treats the request as anonymous.
    """
    return db.session.get(User, int(user_id))
