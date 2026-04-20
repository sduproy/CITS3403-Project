from flask import Flask

from routes import main

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-change-me-before-deploy"
app.register_blueprint(main)


if __name__ == "__main__":
    app.run(debug=True)
