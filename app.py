from pathlib import Path

from flask import Flask

import db
from extensions import db as sa_db, login
import models  # noqa: F401 — registers models with SQLAlchemy at import time
from routes import main


app = Flask(__name__, instance_relative_config=True)
Path(app.instance_path).mkdir(parents=True, exist_ok=True)

db_path = Path(app.instance_path) / "travelplan.sqlite"
app.config.from_mapping(
    SECRET_KEY="dev-change-me-before-deploy",
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_path}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
)

sa_db.init_app(app)
login.init_app(app)
db.init_app(app)
app.register_blueprint(main)


if __name__ == "__main__":
    app.run(debug=True)
