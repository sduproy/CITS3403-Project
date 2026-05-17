# CITS3403-Project SmartVoyage

## Overview

SmartVoyage is an online AI-powered travel itinerary planner that can be used to create, share and view travel itineraries. Users can manually create their itineraries, use AI to create one or just view the most popular ones. Itineraries can be set to private or public, and all public itineraries can be viewed and rated through a user's profile or the community page. 

## Purpose
This website was designed to make travel planning trips simple. Allowing users easy access to detailed itineraries through the AI or publicly shared ones, while allowing more creative or experienced traveller to create their own itinerary and share it for others to see. 

## Features
- **AI itinerary generation** 
  - create a full day-by-day travel plan from just a destination and travel dates
  - Activities, locations, times and descriptions generated automatically
  - Powered by Google Gemini AI

- **Manual itinerary editor**  
  - build and edit itineraries from scratch
  - Add and remove days and activities dynamically
  - Pre-populated with existing data when editing

- **Trip details**
  - Day-by-day activity timeline with times, locations and descriptions
  - Interactive map showing all activity locations
  - Print-friendly layout for taking your plan offline

- **Community page** 
  - Browse and discover public itineraries from other users
  - Filter by trending destinations
  - View any itinerary directly from the community feed

- **Interactive map**  
  - Easily find location of each activity
  - Click activities to fly to their location on the map

- **Reviews & ratings** 
  - One review per user per itinerary
  - Star ratings and comments

- **Personal dashboard** 
  - Toggle public/private instantly
  - View your own itineraries
  - Delete unwanted itineraries of your own

- **Admin dashboard** 
  - Delete any user, itinerary or review

- **User profiles** 
  - View any user's public itineraries


## Group Members
| UWA ID | Name | GitHub Username |
|--------|------|-----------------|
| 24314165 | Sean Du | sduproy |
| 24246563 | Sakindu Dassanayake | sakindudassanayake-arch |
| 24483305 | Voon Yan Kho | VoonYan |
| 24467305 | Robert Turner | vfbmdcccxciii |

## First-time setup

```bash

# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Mac/Linux

# 2. Clone, then install all the deps from requirements.txt.
pip install -r requirements.txt

# 3. (Optional, recommended) generate a real SECRET_KEY and put it in .env.
#    Without this the loud "dev-only-INSECURE..." fallback kicks in.
cp .env.example .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env

# 4a. (Optional) drop your Google AI Studio key into .env so /itinerary/new
#    can call Gemini. Without it the AI route flashes an error and refuses.
echo "GOOGLE_API_KEY=<paste-from-aistudio.google.com/app/apikey>" >> .env

# 4b. (Optional but recommended) Pixabay key for higher-quality
#     destination photos on itinerary cards. Without it, cards
#     fall back to loremflickr (lower quality but still works).
#     Free signup: https://pixabay.com/api/docs/
echo "PIXABAY_API_KEY=<paste-from-pixabay-api-docs>" >> .env


# 5. Just run. bootstrap_db() applies every migration on startup and
#    seeds the admin user from your .env on the first boot.
python -m flask --app app.py run
```

`flask init-db` (the destructive reset) is still available if you want to nuke
local state and start from scratch.

**Default admin login** (seeded on first boot from `.env.example`): username
`admin`, password `admin`. The credentials live in three env vars
(`ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`) — change them in `.env`
to anything you like. If `ADMIN_PASSWORD` is unset, no admin is seeded.



## Tech stack at a glance

| Layer | Library |
|---|---|
| Web framework | Flask |
| Auth (sessions) | Flask-Login |
| Forms + CSRF | Flask-WTF + WTForms |
| ORM | Flask-SQLAlchemy |
| Migrations | Flask-Migrate (Alembic) |
| AI itinerary generation | google-genai (Gemini 3.1 Flash Lite via AI Studio) |
| Templates | Jinja2 + Bootstrap 5 |
| Password hashing | werkzeug.security (pbkdf2:sha256) |
| Database | SQLite (single file at `instance/travelplan.sqlite`) |
| Destination images | Pixabay API (server-side proxy) |
| Interactive maps | Leaflet 1.9.4 (via unpkg CDN) |
| Client-side JS | Vanilla JavaScript + Fetch API (AJAX) |



The architecture follows the MVC pattern from the lectures: `models.py` is
the model layer, `templates/*.html` is the view, and `routes.py` is the
controller (with `forms.py` and `gemini.py` as adjacent helpers).


## Running Tests

### Unit Tests

Run all unit tests:
```bash
python -m unittest discover tests -v
```

Run a specific unit test file:
```bash
python -m unittest tests.test_models -v
python -m unittest tests.test_routes -v
```

### Selenium Tests

Selenium tests require Google Chrome to be installed. 

Run all Selenium tests:
```bash
python -m unittest tests.test_selenium -v
```

Run a specific Selenium test:
```bash
python -m unittest tests.test_selenium.SeleniumTests.test_name_here -v
```

### All Tests
Run all tests:
```bash
python -m unittest discover tests -v
```