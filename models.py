"""
SQLAlchemy ORM models.

These mirror the tables defined in ``schema.sql`` exactly, so existing
``instance/travelplan.sqlite`` databases keep working without any
migration. The only difference is that queries now go through the ORM
(``User.query.filter_by(...)``) instead of raw sqlite3 cursors, which
the Flask security lecture flags as the recommended pattern for
avoiding SQL-injection-style attacks.

Phase B (Flask-Login):
- ``User`` inherits from ``UserMixin``, which provides the four
  properties Flask-Login expects on a user model: ``is_authenticated``,
  ``is_active``, ``is_anonymous``, and ``get_id()``.
- ``load_user`` is registered as the ``@login.user_loader`` callback,
  so Flask-Login can rehydrate the current user from the session
  cookie on every request.
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

    # Cascading children, matching ON DELETE CASCADE in schema.sql.
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
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
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
