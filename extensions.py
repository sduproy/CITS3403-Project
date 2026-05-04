"""
Flask extensions, instantiated without an app.

These objects are bound to the Flask app later via their ``init_app(app)``
method (see ``app.py``). Keeping them in their own module avoids circular
imports — ``models.py`` and ``app.py`` can both import ``db`` from here
without importing each other.
"""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
