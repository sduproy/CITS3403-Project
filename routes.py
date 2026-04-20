from flask import Blueprint, render_template

main = Blueprint("main", __name__)


@main.route("/")
def index():
    return render_template("itinerary.html")


@main.route("/community")
def community():
    return render_template("Popular.html")


# Route stubs to add as features land:
#   /register, /login, /logout             (auth)
#   /dashboard                             (user's saved itineraries)
#   /itinerary/new, /itinerary/<int:id>    (AI generation + detail page)
#   /admin, /admin/users, /admin/itineraries  (admin dashboard)
