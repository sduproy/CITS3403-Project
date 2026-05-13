# CITS3403-Project

CITS3403 Semester Project — SmartVoyage, an AI-powered travel itinerary planner
built on Flask + Flask-SQLAlchemy + Flask-Login + Flask-WTF + Flask-Migrate +
SQLite.

## First-time setup

```bash
# 1. Clone, then install all the deps from requirements.txt.
pip install -r requirements.txt

# 2. (Optional, recommended) generate a real SECRET_KEY and put it in .env.
#    Without this the loud "dev-only-INSECURE..." fallback kicks in.
cp .env.example .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env

# 3. (Optional) drop your Google AI Studio key into .env so /itinerary/new
#    can call Gemini. Without it the AI route flashes an error and refuses.
echo "GOOGLE_API_KEY=<paste-from-aistudio.google.com/app/apikey>" >> .env

# 4. Just run. bootstrap_db() applies every migration on startup and
#    seeds the admin user (admin / admin) on the first boot.
python -m flask --app app.py run
```

`flask init-db` (the destructive reset) is still available if you want to nuke
local state and start from scratch.

## Database migrations — the workflow that replaces "delete and reinit"

The project uses **Flask-Migrate** (Alembic) to version the database schema.
The migration scripts live in `migrations/versions/`. Each one has an
`upgrade()` and `downgrade()` so we can move forward and backward in schema
history without losing existing data.

### When you pull someone else's schema change

```bash
git pull
python -m flask --app app.py run   # bootstrap_db runs `flask db upgrade` for you
```

That's it — your existing rows are preserved. **Don't delete
`instance/travelplan.sqlite` unless you actually want to wipe local data.**

If you'd rather apply migrations explicitly without starting the server:

```bash
python -m flask --app app.py db upgrade
```

### When YOU change the schema (new column, new table, etc.)

1. Edit the relevant model in `models.py` — add the column / class / constraint.
2. Auto-generate the migration:

   ```bash
   python -m flask --app app.py db migrate -m "describe what changed"
   ```

   Alembic compares the new model definitions against your DB's current
   schema and writes a new file in `migrations/versions/`.

3. Open the generated file and **read it before committing**. Alembic gets
   most things right, but column renames and type changes sometimes need
   manual tweaks (the auto-generator can't always tell a rename apart from
   a drop + add). The slide says exactly this: *"sometimes!"* it's automatic.

4. Apply it locally to verify it works:

   ```bash
   python -m flask --app app.py db upgrade
   ```

5. Commit BOTH the model change and the migration script in the same commit.

### Useful commands

| Command | What |
|---|---|
| `flask db current` | Which migration is the DB currently on? |
| `flask db history` | Full chain of migrations in this branch |
| `flask db heads` | Tip(s) of the migration history |
| `flask db downgrade` | Roll back one migration |
| `flask db downgrade base` | Roll back ALL migrations (back to empty) |
| `flask db upgrade` | Apply all pending migrations |
| `flask db migrate -m "..."` | Auto-generate a new migration from current model state |
| `flask db revision -m "..."` | Make an empty migration script you fill in by hand |

### Common gotchas

- **"`flask db migrate` says no changes detected"** — bootstrap_db's
  `upgrade()` already brought the DB in sync with the models BEFORE Alembic
  ran the comparison. This shouldn't happen unless something else
  recreated the schema; if it does, drop the DB (`rm
  instance/travelplan.sqlite`) and try again.
- **"sqlite3.OperationalError: no such column"** when running `flask db
  migrate` — the models are ahead of the DB and bootstrap_db's seed query
  is failing on the missing column. The function catches this and skips the
  seed; if it doesn't, your DB is in a weird intermediate state — re-run
  `flask db upgrade` to land at HEAD, then try again.
- **A teammate force-pushed a migration that conflicts with yours** —
  one of you needs to `flask db downgrade` to before the conflict, then
  re-generate. Migration filenames embed random Alembic revision IDs, so
  two parallel branches always conflict if they both touch the schema.

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

The architecture follows the MVC pattern from the lectures: `models.py` is
the model layer, `templates/*.html` is the view, and `routes.py` is the
controller (with `forms.py` and `gemma.py` as adjacent helpers).
