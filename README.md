# Tracky

Tracky is a personal movie and TV show tracker built with Python, Flask, SQLAlchemy, Jinja2, HTML, CSS, and minimal vanilla JavaScript. It is designed for one authenticated user and a persistent database, with timeline, library, favorites, search, item details, editing, check tools, and statistics.

## Features

- Session-based authentication with credentials from configuration.
- No public registration.
- Persistent database support through SQLAlchemy.
- TMDb search, manual imports, and correction from TMDb links.
- Editable metadata and personal fields.
- Check workflow for reviewing TMDb matches and personal scores.
- Configurable personal rating scale through `PERSONAL_SCORE_MIN` and `PERSONAL_SCORE_MAX`.
- Dashboard, timeline, library, favorites, local/TMDb search, details, edit forms, and statistics.
- Filters for media type, genre, favorites, personal rating, watched year, and title.
- Light mode and dark mode.
- Responsive UI for desktop, tablet, and phone.

## Visual Identity

Tracky uses a minimal media-timeline mark:

- Logo: `tracky/static/img/logo.svg`
- Favicon: `tracky/static/img/favicon.svg`
- Application icon: `tracky/static/img/app-icon.svg`

Palette:

- Ink: `#181816`
- Paper: `#F7F6F2`
- Surface: `#FFFFFF`
- Line: `#D8D2C5`
- Amber accent: `#D9A441`
- Green signal: `#3F7D5A`
- Blue secondary: `#4E718B`

Typography suggestion:

- Primary: Inter
- Fallback: system UI stack
- Display style: tight but not condensed, with standard letter spacing

## Project Structure

```text
api/index.py                  Vercel Python entry point
run.py                        Local Flask entry point
tracky/
  __init__.py                 App factory and error handling
  auth.py                     Login and logout routes
  config.py                   Environment-driven configuration
  extensions.py               Flask-SQLAlchemy instance
  models.py                   SQLAlchemy models and relationships
  routes.py                   Application routes and forms
  services/
    metadata.py               TMDb metadata enrichment helpers
    statistics.py             Aggregated statistics
    tmdb.py                   TMDb API client
  static/                     CSS, JavaScript, logo, favicon, app icon
  templates/                  Jinja2 templates
scripts/
  load_initial_database.py    One-time local SQLite to persistent DB loader
tests/                        Automated tests
```

## Installation

Use Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Generate a password hash:

```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password'))"
```

Copy the generated value into `.env` as `APP_PASSWORD_HASH`.

## Configuration

Required values:

```env
SECRET_KEY=replace-with-a-long-random-secret
APP_USERNAME=your-username
APP_PASSWORD_HASH=generated-password-hash
TMDB_API_KEY=your-tmdb-api-key
```

Optional values:

```env
DATABASE_URL=postgresql://user:password@host/database?sslmode=require
PERSONAL_SCORE_MIN=1
PERSONAL_SCORE_MAX=10
TRACKY_TMDB_LANGUAGE=it-IT
```

`DATABASE_URL` can also be a local SQLite URL for development, for example `sqlite:///instance/tracky.sqlite3`. For Vercel production, use a persistent external database such as Neon Postgres.

## TMDb API Key

Create a TMDb account and generate an API key from the TMDb developer settings. Tracky uses it to:

- Search movies and TV shows.
- Fetch Italian localized titles and overviews.
- Fetch original titles, genres, directors or creators, cast, release dates, ratings, vote counts, posters, and backdrops.

If `TMDB_API_KEY` is missing, TMDb search and enrichment are disabled.

## Running Locally

```bash
flask --app run.py run --debug
```

Open `http://127.0.0.1:5000`.

By default in local development, Tracky uses `instance/tracky.sqlite3` when `DATABASE_URL` is not set.

For production-like local testing, set `DATABASE_URL` to the same persistent database URL used on Vercel.

## Initial Database Load

The historical SQLite database is local bootstrap data only. It is not required by the Flask app at runtime.

Run the one-time load from your local machine, pointing the source to your local SQLite file and the target to the persistent database:

```bash
DATABASE_URL='postgresql://user:password@host/database?sslmode=require' \
python scripts/load_initial_database.py --source-url sqlite:///data/tracky.seed.sqlite3
```

The script creates the Tracky schema, copies the existing media data, preserves settings such as check progress, and creates the configured `APP_USERNAME` user if needed. It refuses to copy into a database that already contains Tracky data. Use `--force` only when you intentionally want to replace the target data tables.

After the persistent database has been populated, keep `data/tracky.seed.sqlite3` local only. It should not be deployed or committed.

## Vercel Deployment

The project includes:

- `api/index.py`
- `vercel.json`
- `requirements.txt`

Set the same environment variables in Vercel project settings. The default Vercel Python entry point imports the Flask app from `tracky.create_app()`.

Use a persistent external `DATABASE_URL` in Vercel. A writable SQLite file inside a Vercel serverless function is not a permanent library.

Future corrections can be made from Search, Check, or the item edit form. They are permanent when `DATABASE_URL` points to the persistent database.

## Testing

```bash
pytest
```

The suite covers:

- Authentication.
- TMDb client mapping.
- SQLAlchemy model relationships.
- Local search by Italian and original title.
- Favorites filtering.
- Alphabetical sorting.
- Statistics aggregation.

## Future Improvements

- Background TMDb enrichment jobs for very large libraries.
- Advanced charts with a small progressive-enhancement JavaScript layer.
- CSV or JSON export from the persistent library.
