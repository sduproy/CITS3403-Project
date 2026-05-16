"""
seed_community.py — populate the database with sample public itineraries.

Run via:

    flask seed-community

so the /community page and the trending chips have content to display
from a fresh checkout. Idempotent: if any showcase user already exists
the command exits without inserting duplicates.

Each itinerary's ``content`` column stores JSON that matches the schema
in ``gemini.py`` (Activity / Day / ItineraryPlan), so ``trip_details.html``
renders these the same way it renders AI-generated ones.

Destinations intentionally overlap (Bali x2, Tokyo x2) so the
/api/trending endpoint returns counts greater than 1 for the most-popular
chips — otherwise every destination would tie at count 1 and the trending
display would look uninformative.
"""

import json
from datetime import datetime, timedelta

import click
from werkzeug.security import generate_password_hash

from extensions import db
from models import Itinerary, Review, User


# ── Showcase user accounts ─────────────────────────────────────────────
# Real-looking usernames so community cards don't all say "admin".
# All share the same showcase password — these are demo accounts.

SHOWCASE_USERS = [
    {"username": "anna_voyage",   "email": "anna@smartvoyage.local"},
    {"username": "marco_trips",   "email": "marco@smartvoyage.local"},
    {"username": "lena_explore",  "email": "lena@smartvoyage.local"},
    {"username": "carlos_wander", "email": "carlos@smartvoyage.local"},
]

SHOWCASE_PASSWORD = "showcase"


# ── Pre-built itinerary plans ──────────────────────────────────────────
# Each builder takes the trip's first day as a date and returns a JSON
# string matching gemini.py's ItineraryPlan schema.

def _plan_json(destination, summary, days):
    return json.dumps({
        "destination": destination,
        "summary": summary,
        "days": days,
    })


def _bali_plan(start_date):
    d = [start_date + timedelta(days=i) for i in range(3)]
    return _plan_json(
        "Bali",
        "Three days of jungle, temples and beaches in the heart of Bali.",
        [
            {
                "day_number": 1,
                "date": d[0].strftime("%Y-%m-%d"),
                "title": "Ubud arrival & rice terraces",
                "activities": [
                    {"time": "10:00", "title": "Tegallalang Rice Terraces", "description": "Walk the iconic stepped paddies.", "location": "Ubud", "duration_minutes": 90},
                    {"time": "13:00", "title": "Sacred Monkey Forest", "description": "Wander among 700 long-tailed macaques.", "location": "Ubud", "duration_minutes": 60},
                    {"time": "17:00", "title": "Sunset at Campuhan Ridge", "description": "Easy ridge walk with valley views.", "location": "Ubud", "duration_minutes": 75},
                ],
            },
            {
                "day_number": 2,
                "date": d[1].strftime("%Y-%m-%d"),
                "title": "Temples & waterfalls",
                "activities": [
                    {"time": "08:30", "title": "Tirta Empul Temple", "description": "Holy spring water purification ritual.", "location": "Tampaksiring", "duration_minutes": 90},
                    {"time": "11:30", "title": "Tegenungan Waterfall", "description": "Short hike to a tropical waterfall.", "location": "Sukawati", "duration_minutes": 90},
                    {"time": "15:00", "title": "Tanah Lot at sunset", "description": "Iconic sea temple silhouetted against the horizon.", "location": "Tabanan", "duration_minutes": 120},
                ],
            },
            {
                "day_number": 3,
                "date": d[2].strftime("%Y-%m-%d"),
                "title": "Beach day in Seminyak",
                "activities": [
                    {"time": "09:00", "title": "Surf lesson", "description": "Beginner-friendly waves at Seminyak Beach.", "location": "Seminyak", "duration_minutes": 120},
                    {"time": "13:00", "title": "Beachfront lunch", "description": "Local Indonesian dishes with a sea view.", "location": "Seminyak", "duration_minutes": 90},
                    {"time": "17:00", "title": "Sunset cocktails at La Plancha", "description": "Beanbags on the sand, beers in hand.", "location": "Seminyak", "duration_minutes": 90},
                ],
            },
        ],
    )


def _bali_short_plan(start_date):
    d = [start_date + timedelta(days=i) for i in range(2)]
    return _plan_json(
        "Bali",
        "A quick two-day Bali escape focused on Uluwatu and the southern beaches.",
        [
            {
                "day_number": 1,
                "date": d[0].strftime("%Y-%m-%d"),
                "title": "Uluwatu cliffs & beach clubs",
                "activities": [
                    {"time": "11:00", "title": "Padang Padang Beach", "description": "Tucked-away cove with crystal water.", "location": "Uluwatu", "duration_minutes": 120},
                    {"time": "15:00", "title": "Single Fin sunset", "description": "Cliffside bar with Indian Ocean views.", "location": "Uluwatu", "duration_minutes": 120},
                    {"time": "19:00", "title": "Uluwatu Temple kecak dance", "description": "Traditional fire-dance against the sunset.", "location": "Uluwatu", "duration_minutes": 90},
                ],
            },
            {
                "day_number": 2,
                "date": d[1].strftime("%Y-%m-%d"),
                "title": "Nusa Penida day trip",
                "activities": [
                    {"time": "07:00", "title": "Fast boat to Nusa Penida", "description": "Quick crossing from Sanur harbour.", "location": "Sanur", "duration_minutes": 45},
                    {"time": "09:00", "title": "Kelingking Beach viewpoint", "description": "The famous T-Rex shaped cliff.", "location": "Nusa Penida", "duration_minutes": 90},
                    {"time": "12:00", "title": "Angel's Billabong", "description": "Natural rock pool overlooking the ocean.", "location": "Nusa Penida", "duration_minutes": 90},
                ],
            },
        ],
    )


def _tokyo_plan(start_date):
    d = [start_date + timedelta(days=i) for i in range(3)]
    return _plan_json(
        "Tokyo",
        "Neon, sushi and temples — a fast-paced three-day Tokyo sampler.",
        [
            {
                "day_number": 1,
                "date": d[0].strftime("%Y-%m-%d"),
                "title": "Shibuya & Shinjuku",
                "activities": [
                    {"time": "10:00", "title": "Shibuya Crossing & Hachiko statue", "description": "The world's busiest pedestrian crossing.", "location": "Shibuya", "duration_minutes": 60},
                    {"time": "13:00", "title": "Sushi lunch at Uobei", "description": "Bullet-train conveyor-belt sushi.", "location": "Shibuya", "duration_minutes": 60},
                    {"time": "19:00", "title": "Omoide Yokocho izakaya alley", "description": "Lantern-lit yakitori bars under the train tracks.", "location": "Shinjuku", "duration_minutes": 120},
                ],
            },
            {
                "day_number": 2,
                "date": d[1].strftime("%Y-%m-%d"),
                "title": "Asakusa & Akihabara",
                "activities": [
                    {"time": "09:00", "title": "Senso-ji Temple", "description": "Tokyo's oldest Buddhist temple, lined with snack stalls.", "location": "Asakusa", "duration_minutes": 90},
                    {"time": "12:00", "title": "Tokyo Skytree", "description": "634m observation deck for sweeping city views.", "location": "Sumida", "duration_minutes": 90},
                    {"time": "15:00", "title": "Akihabara electronics & arcades", "description": "Eight floors of retro games at Super Potato.", "location": "Akihabara", "duration_minutes": 180},
                ],
            },
            {
                "day_number": 3,
                "date": d[2].strftime("%Y-%m-%d"),
                "title": "Harajuku & Meiji Jingu",
                "activities": [
                    {"time": "10:00", "title": "Meiji Jingu Shrine", "description": "Forested Shinto shrine in the heart of the city.", "location": "Shibuya", "duration_minutes": 90},
                    {"time": "13:00", "title": "Takeshita Street", "description": "Crepes, kawaii fashion and rainbow cotton candy.", "location": "Harajuku", "duration_minutes": 120},
                    {"time": "17:00", "title": "Yoyogi Park sunset", "description": "A calm finish to a busy day.", "location": "Yoyogi", "duration_minutes": 60},
                ],
            },
        ],
    )


def _tokyo_kyoto_plan(start_date):
    d = [start_date + timedelta(days=i) for i in range(2)]
    return _plan_json(
        "Tokyo",
        "Whirlwind two-day Tokyo highlights with a day trip to Mt. Fuji.",
        [
            {
                "day_number": 1,
                "date": d[0].strftime("%Y-%m-%d"),
                "title": "Modern Tokyo",
                "activities": [
                    {"time": "10:00", "title": "TeamLab Planets", "description": "Immersive digital art installation.", "location": "Toyosu", "duration_minutes": 120},
                    {"time": "14:00", "title": "Tsukiji Outer Market lunch", "description": "Fresh tuna donburi and tamagoyaki.", "location": "Tsukiji", "duration_minutes": 90},
                    {"time": "18:00", "title": "Roppongi Hills observation deck", "description": "Skyline views including Tokyo Tower.", "location": "Roppongi", "duration_minutes": 60},
                ],
            },
            {
                "day_number": 2,
                "date": d[1].strftime("%Y-%m-%d"),
                "title": "Mt. Fuji day trip",
                "activities": [
                    {"time": "08:00", "title": "Bus to Lake Kawaguchi", "description": "Direct express from Shinjuku.", "location": "Shinjuku", "duration_minutes": 120},
                    {"time": "11:00", "title": "Chureito Pagoda viewpoint", "description": "Pagoda framed by Mt. Fuji.", "location": "Fujiyoshida", "duration_minutes": 90},
                    {"time": "14:00", "title": "Lake Kawaguchi walk", "description": "Lakeshore stroll with Fuji reflections.", "location": "Fujikawaguchiko", "duration_minutes": 120},
                ],
            },
        ],
    )


def _paris_plan(start_date):
    d = [start_date + timedelta(days=i) for i in range(2)]
    return _plan_json(
        "Paris",
        "Two romantic days hitting the Paris classics, light on queues.",
        [
            {
                "day_number": 1,
                "date": d[0].strftime("%Y-%m-%d"),
                "title": "Left Bank classics",
                "activities": [
                    {"time": "09:00", "title": "Eiffel Tower at opening", "description": "Beat the lines with the first lift slot.", "location": "Champ de Mars", "duration_minutes": 120},
                    {"time": "13:00", "title": "Lunch in Saint-Germain", "description": "Onion soup and steak frites at a corner brasserie.", "location": "Saint-Germain-des-Pres", "duration_minutes": 90},
                    {"time": "16:00", "title": "Musee d'Orsay", "description": "Impressionists in a converted train station.", "location": "7th arrondissement", "duration_minutes": 150},
                ],
            },
            {
                "day_number": 2,
                "date": d[1].strftime("%Y-%m-%d"),
                "title": "Marais & Montmartre",
                "activities": [
                    {"time": "10:00", "title": "Place des Vosges", "description": "Oldest planned square in Paris.", "location": "Le Marais", "duration_minutes": 60},
                    {"time": "13:00", "title": "Falafel at L'As du Fallafel", "description": "Iconic queue, worth it.", "location": "Le Marais", "duration_minutes": 60},
                    {"time": "17:00", "title": "Sacre-Coeur at sunset", "description": "Watch the city light up from Montmartre's steps.", "location": "Montmartre", "duration_minutes": 120},
                ],
            },
        ],
    )


def _greece_plan(start_date):
    d = [start_date + timedelta(days=i) for i in range(3)]
    return _plan_json(
        "Greece",
        "Three days of white-and-blue island hopping in the Cyclades.",
        [
            {
                "day_number": 1,
                "date": d[0].strftime("%Y-%m-%d"),
                "title": "Oia & Fira",
                "activities": [
                    {"time": "11:00", "title": "Oia village walk", "description": "Wander whitewashed alleys and blue domes.", "location": "Oia, Santorini", "duration_minutes": 120},
                    {"time": "15:00", "title": "Wine tasting at Santo Wines", "description": "Cliffside Assyrtiko with caldera views.", "location": "Pyrgos", "duration_minutes": 90},
                    {"time": "19:00", "title": "Oia sunset", "description": "The most-photographed sunset in the world.", "location": "Oia", "duration_minutes": 60},
                ],
            },
            {
                "day_number": 2,
                "date": d[1].strftime("%Y-%m-%d"),
                "title": "Akrotiri & Red Beach",
                "activities": [
                    {"time": "10:00", "title": "Akrotiri archaeological site", "description": "Minoan Bronze Age 'Pompeii of the Aegean'.", "location": "Akrotiri", "duration_minutes": 120},
                    {"time": "13:00", "title": "Red Beach swim", "description": "Iron-red cliffs over volcanic sand.", "location": "Akrotiri", "duration_minutes": 120},
                ],
            },
            {
                "day_number": 3,
                "date": d[2].strftime("%Y-%m-%d"),
                "title": "Day trip to Mykonos",
                "activities": [
                    {"time": "08:00", "title": "Ferry to Mykonos", "description": "Fast catamaran across the Aegean.", "location": "Athinios Port", "duration_minutes": 150},
                    {"time": "13:00", "title": "Little Venice waterfront", "description": "Lunch with waves lapping at your feet.", "location": "Mykonos Town", "duration_minutes": 120},
                    {"time": "17:00", "title": "Mykonos windmills", "description": "The iconic five Kato Mili windmills.", "location": "Mykonos Town", "duration_minutes": 60},
                ],
            },
        ],
    )


def _morocco_plan(start_date):
    d = [start_date + timedelta(days=i) for i in range(2)]
    return _plan_json(
        "Morocco",
        "Marrakech medinas and a glimpse of the Sahara in two packed days.",
        [
            {
                "day_number": 1,
                "date": d[0].strftime("%Y-%m-%d"),
                "title": "Marrakech medina",
                "activities": [
                    {"time": "10:00", "title": "Jardin Majorelle", "description": "Cobalt-blue garden once owned by Yves Saint Laurent.", "location": "Gueliz", "duration_minutes": 90},
                    {"time": "14:00", "title": "Souks of the medina", "description": "Wander the dyeing, leather and spice quarters.", "location": "Medina", "duration_minutes": 180},
                    {"time": "19:00", "title": "Jemaa el-Fnaa night market", "description": "Snake charmers, storytellers and tagine stalls.", "location": "Medina", "duration_minutes": 120},
                ],
            },
            {
                "day_number": 2,
                "date": d[1].strftime("%Y-%m-%d"),
                "title": "Agafay Desert day trip",
                "activities": [
                    {"time": "09:00", "title": "Camel ride at sunrise", "description": "Berber-led trek through rocky desert.", "location": "Agafay", "duration_minutes": 120},
                    {"time": "13:00", "title": "Lunch in a Berber tent", "description": "Tagine, mint tea and bread fresh from the fire.", "location": "Agafay", "duration_minutes": 90},
                    {"time": "16:00", "title": "Atlas Mountains viewpoint", "description": "Drive back via the foothills.", "location": "High Atlas", "duration_minutes": 60},
                ],
            },
        ],
    )


def _iceland_plan(start_date):
    d = [start_date + timedelta(days=i) for i in range(2)]
    return _plan_json(
        "Iceland",
        "Two days of glaciers, hot springs and the Golden Circle.",
        [
            {
                "day_number": 1,
                "date": d[0].strftime("%Y-%m-%d"),
                "title": "Golden Circle",
                "activities": [
                    {"time": "09:00", "title": "Thingvellir National Park", "description": "Walk between the Eurasian and North American plates.", "location": "Thingvellir", "duration_minutes": 120},
                    {"time": "13:00", "title": "Geysir hot spring area", "description": "Watch Strokkur erupt every 5-10 minutes.", "location": "Haukadalur", "duration_minutes": 90},
                    {"time": "16:00", "title": "Gullfoss waterfall", "description": "Two-tiered cascade plunging into a canyon.", "location": "Bru", "duration_minutes": 90},
                ],
            },
            {
                "day_number": 2,
                "date": d[1].strftime("%Y-%m-%d"),
                "title": "Blue Lagoon & Reykjavik",
                "activities": [
                    {"time": "10:00", "title": "Blue Lagoon geothermal spa", "description": "Milky-blue silica waters and a swim-up bar.", "location": "Grindavik", "duration_minutes": 180},
                    {"time": "15:00", "title": "Hallgrimskirkja church", "description": "Basalt-column-inspired Lutheran landmark.", "location": "Reykjavik", "duration_minutes": 60},
                    {"time": "20:00", "title": "Northern Lights chase", "description": "Aurora hunt if KP index cooperates.", "location": "Outside Reykjavik", "duration_minutes": 180},
                ],
            },
        ],
    )


# ── Itinerary specs ────────────────────────────────────────────────────
# (username, destination string saved to the DB, plan builder, arrive_time, leave_time)
# Destinations intentionally repeat for Bali and Tokyo so trending shows
# counts greater than 1.
#
# Each spec carries a stable string "key" so REVIEWS_SPEC below can attach
# fake reviews to a specific trip by name rather than by list index — much
# less fragile if the list is ever reordered.

ITINERARIES_SPEC = [
    {"key": "anna_bali",      "username": "anna_voyage",   "destination": "Bali",    "plan_fn": _bali_plan,        "arrive": datetime(2026, 6, 5, 10, 0),  "leave": datetime(2026, 6, 7, 18, 0)},
    {"key": "marco_bali",     "username": "marco_trips",   "destination": "Bali",    "plan_fn": _bali_short_plan,  "arrive": datetime(2026, 7, 12, 9, 0),  "leave": datetime(2026, 7, 13, 20, 0)},
    {"key": "lena_tokyo",     "username": "lena_explore",  "destination": "Tokyo",   "plan_fn": _tokyo_plan,       "arrive": datetime(2026, 8, 1, 8, 0),   "leave": datetime(2026, 8, 3, 21, 0)},
    {"key": "carlos_tokyo",   "username": "carlos_wander", "destination": "Tokyo",   "plan_fn": _tokyo_kyoto_plan, "arrive": datetime(2026, 9, 14, 11, 0), "leave": datetime(2026, 9, 15, 22, 0)},
    {"key": "anna_paris",     "username": "anna_voyage",   "destination": "Paris",   "plan_fn": _paris_plan,       "arrive": datetime(2026, 5, 20, 13, 0), "leave": datetime(2026, 5, 21, 19, 0)},
    {"key": "marco_greece",   "username": "marco_trips",   "destination": "Greece",  "plan_fn": _greece_plan,      "arrive": datetime(2026, 6, 25, 12, 0), "leave": datetime(2026, 6, 27, 20, 0)},
    {"key": "lena_morocco",   "username": "lena_explore",  "destination": "Morocco", "plan_fn": _morocco_plan,     "arrive": datetime(2026, 10, 3, 9, 0),  "leave": datetime(2026, 10, 4, 21, 0)},
    {"key": "carlos_iceland", "username": "carlos_wander", "destination": "Iceland", "plan_fn": _iceland_plan,     "arrive": datetime(2026, 11, 10, 7, 0), "leave": datetime(2026, 11, 11, 22, 0)},
]


# ── Review specs ───────────────────────────────────────────────────────
# Fake reviews for the demo so /community has a mix of rated and
# unrated trips. Two trips (carlos_tokyo, lena_morocco) are deliberately
# left unreviewed — that way the "Top rated" client-side sort visibly
# moves rated trips upward while unrated ones drop to the bottom, which
# makes the sorting feature obvious during the presentation.
#
# Constraints respected:
#   - reviewers are all seed users (anna_voyage, marco_trips, lena_explore,
#     carlos_wander), matching the "real reviews from real users" spirit
#   - no user reviews their own trip (the submit_review route enforces
#     this on real reviews too — seeding the same way keeps the demo DB
#     a valid state the running app could have produced organically)
#   - the (itinerary_id, user_id) UNIQUE constraint on the reviews table
#     means at most one review per (trip, user) pair — none repeat below
#
# Comments reference specific activities/locations from each plan so they
# read like a human who actually went on the trip, and tone is varied
# (5-star raves, mid 3-star with criticism) so it doesn't feel astroturfed.

REVIEWS_SPEC = [
    # anna_bali — 2 reviews, avg 4.5
    {"itinerary_key": "anna_bali", "reviewer": "marco_trips", "rating": 4,
     "comment": "Loved Tegallalang and Tanah Lot at sunset — both lived up to the hype. Day one runs hot with the ridge walk after the monkey forest though; would swap Campuhan to a morning slot."},
    {"itinerary_key": "anna_bali", "reviewer": "carlos_wander", "rating": 5,
     "comment": "Nice mix of culture and beach. The Tirta Empul ritual was the unexpected highlight for me, and ending at La Plancha with sand in your toes is exactly the right way to wrap a Bali trip."},

    # marco_bali — 1 review, avg 5.0
    {"itinerary_key": "marco_bali", "reviewer": "lena_explore", "rating": 5,
     "comment": "Nusa Penida from Sanur is the move. Kelingking Beach genuinely lives up to the photos. Single Fin at sunset is mandatory — go early for a cliff-edge spot."},

    # lena_tokyo — 3 reviews, avg 4.7
    {"itinerary_key": "lena_tokyo", "reviewer": "anna_voyage", "rating": 5,
     "comment": "First-afternoon Shibuya then Hachiko then conveyor sushi is the perfect orientation. Omoide Yokocho at night honestly felt like stepping onto a film set."},
    {"itinerary_key": "lena_tokyo", "reviewer": "carlos_wander", "rating": 5,
     "comment": "The Asakusa morning routine works — get to Senso-ji at opening and you can actually photograph the lanterns without a thousand selfies in frame. Skytree is overpriced but the view doesn't lie."},
    {"itinerary_key": "lena_tokyo", "reviewer": "marco_trips", "rating": 4,
     "comment": "Excellent first two days. Day three was a bit muted by comparison — Meiji Jingu is lovely but Yoyogi Park at sunset felt like filler. Would swap for Shimokita or Daikanyama."},

    # carlos_tokyo — DELIBERATELY UNREVIEWED for the sort demo

    # anna_paris — 2 reviews, avg 3.5
    {"itinerary_key": "anna_paris", "reviewer": "lena_explore", "rating": 4,
     "comment": "Eiffel at opening saved us a 90-min queue. d'Orsay over the Louvre is the right call for two days. Felt rushed in the Marais though — would add half a day."},
    {"itinerary_key": "anna_paris", "reviewer": "marco_trips", "rating": 3,
     "comment": "Two days isn't really enough for Paris, and this itinerary feels the squeeze. Sacre-Coeur sunset is beautiful but the rest of the day flies past. Worth padding to three days if you can."},

    # marco_greece — 1 review, avg 5.0
    {"itinerary_key": "marco_greece", "reviewer": "anna_voyage", "rating": 5,
     "comment": "Oia sunset earned every cliché. Santo Wines as a pre-sunset stop is the right call — you arrive at the caldera already loose. The Mykonos day-trip ferry timing actually works, which surprised me."},

    # lena_morocco — DELIBERATELY UNREVIEWED for the sort demo

    # carlos_iceland — 2 reviews, avg 5.0
    {"itinerary_key": "carlos_iceland", "reviewer": "anna_voyage", "rating": 5,
     "comment": "Hit all three Golden Circle classics with energy to spare. Blue Lagoon at a late evening slot was much quieter than the daytime crush — book the last entry."},
    {"itinerary_key": "carlos_iceland", "reviewer": "marco_trips", "rating": 5,
     "comment": "Aurora chase was a gamble that paid off — KP 4 night, clear sky. Even without the lights, Strokkur erupting on cue every few minutes is one of those just-stand-there moments."},
]


def seed_community_data():
    """Insert showcase users + public itineraries.

    Idempotent: if the first showcase user already exists, returns False
    and does nothing. Otherwise inserts everything in one transaction
    and returns True.
    """
    if User.query.filter_by(username=SHOWCASE_USERS[0]["username"]).first() is not None:
        return False

    user_objs = {}
    for spec in SHOWCASE_USERS:
        user = User(
            username=spec["username"],
            email=spec["email"],
            password_hash=generate_password_hash(SHOWCASE_PASSWORD, method="pbkdf2:sha256"),
            role="user",
        )
        db.session.add(user)
        user_objs[spec["username"]] = user

    db.session.flush()  # assign user IDs without committing yet

    # Insert itineraries, keeping a key -> Itinerary lookup so the reviews
    # loop below can attach a Review to a named trip without having to
    # query it back out of the DB.
    itin_objs = {}
    for itin_spec in ITINERARIES_SPEC:
        owner = user_objs[itin_spec["username"]]
        itinerary = Itinerary(
            user_id=owner.id,
            destination=itin_spec["destination"],
            arrive_time=itin_spec["arrive"],
            leave_time=itin_spec["leave"],
            content=itin_spec["plan_fn"](itin_spec["arrive"].date()),
            is_public=1,
        )
        db.session.add(itinerary)
        itin_objs[itin_spec["key"]] = itinerary

    # Flush so each Itinerary gets its primary-key id assigned. Without
    # this, Review.itinerary_id would be NULL (Itinerary.id is only
    # populated once the row reaches the DB, even before commit).
    db.session.flush()

    for review_spec in REVIEWS_SPEC:
        itinerary = itin_objs[review_spec["itinerary_key"]]
        reviewer = user_objs[review_spec["reviewer"]]
        db.session.add(Review(
            itinerary_id=itinerary.id,
            user_id=reviewer.id,
            rating=review_spec["rating"],
            comment=review_spec["comment"],
        ))

    db.session.commit()
    return True


@click.command("seed-community")
def seed_community_command():
    """Insert sample public itineraries for the community page."""
    inserted = seed_community_data()
    if inserted:
        click.echo(
            f"Seeded {len(SHOWCASE_USERS)} showcase users, "
            f"{len(ITINERARIES_SPEC)} public itineraries, and "
            f"{len(REVIEWS_SPEC)} reviews."
        )
    else:
        click.echo(
            "Showcase data already present — skipping. "
            "(Run `flask init-db` first to wipe the database.)"
        )


def init_app(app):
    """Register the seed-community CLI command on the given Flask app."""
    app.cli.add_command(seed_community_command)
