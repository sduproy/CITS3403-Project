from flask import Flask

from routes import main

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-change-me-before-deploy"
app.register_blueprint(main)


from pathlib import Path

from flask import Flask

import db
from routes import main


app = Flask(__name__, instance_relative_config=True)
app.config.from_mapping(
    SECRET_KEY="dev-change-me-before-deploy",
    DATABASE=str(Path(app.instance_path) / "travelplan.sqlite"),
)
Path(app.instance_path).mkdir(parents=True, exist_ok=True)

db.init_app(app)
app.register_blueprint(main)


if __name__ == "__main__":
    app.run(debug=True)
