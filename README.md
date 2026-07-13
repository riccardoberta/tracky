# Tracky

Tracky is a private movie and TV show tracker built with Python, Flask, SQLAlchemy, Jinja2, HTML, CSS, and minimal vanilla JavaScript. It is designed for one authenticated user, a persistent database, and a focused personal workflow: search, import, correct, rate, browse, analyze, and export a media library.

## Features

- Session-based authentication with credentials from configuration.
- No public registration.
- Persistent database support through SQLAlchemy, with SQLite for local development and Postgres for production.
- Dashboard, timeline, library, favorites, local/TMDb search, item details, edit forms, and statistics.
- TMDb search and imports for movies and TV shows.
- Editable metadata, personal ratings, watched dates, favorite markers, notes, posters, backdrops, genres, directors or creators, and cast.
- Edit and delete actions from item cards and edit pages.
- Filters for media type, genre, favorites, personal rating, watched year, and title.
- Configurable personal rating scale through `PERSONAL_SCORE_MIN` and `PERSONAL_SCORE_MAX`.
- Full JSON export of the application data from the Dashboard.
- Letterboxd CSV export for movies from the Dashboard.
- Light mode and dark mode.
- Responsive UI for desktop, tablet, and phone, with a collapsed mobile/tablet menu.
- Home Screen app metadata and PNG icons for iPhone/iOS saved web apps.
- Safe startup behavior for unknown URLs: unauthenticated users go to login, authenticated users go to the dashboard.

## Exports

Tracky exposes two authenticated export endpoints and links to both from the Dashboard:

- `GET /export.json` downloads `tracky-export-YYYYMMDD-HHMMSS.json`.
  This is a complete structured export with users, genres, people, media items, media-genre links, media-person links, episodes, watch events, media lists, media list items, settings, row counts, and export metadata.
- `GET /export/letterboxd.csv` downloads `tracky-letterboxd-YYYYMMDD-HHMMSS.csv`.
  This includes only movies and uses Letterboxd-compatible CSV columns: `tmdbID`, `imdbID`, `Title`, `Year`, `Directors`, `Rating`, `WatchedDate`, `Rewatch`, `Tags`, and `Review`. Tracky personal ratings are normalized to Letterboxd's 0.5-5 scale.

## Visual Identity

Tracky uses a minimal media-timeline mark:

- Logo: `tracky/static/img/logo.svg`
- Favicon: `tracky/static/img/favicon.svg`
- SVG application icon source: `tracky/static/img/app-icon.svg`
- iOS/Home Screen icons: `tracky/static/img/app-icon-180.png`, `tracky/static/img/app-icon-192.png`, `tracky/static/img/app-icon-512.png`
- Web app manifest: `tracky/static/manifest.webmanifest`
- Shared app icon metadata partial: `tracky/templates/_app_icons.html`

Palette:

- Ink: `#181816`
- Paper: `#F7F6F2`
- Surface: `#FFFFFF`
- Line: `#D8D2C5`
- Amber accent: `#D9A441`
- Green signal: `#3F7D5A`
- Blue secondary: `#4E718B`

Typography:

- Primary: Inter
- Fallback: system UI stack
- Display style: tight but not condensed, with standard letter spacing

## Project Structure

```text
api/index.py                  Vercel Python entry point
run.py                        Local Flask entry point
tracky/
  __init__.py                 App factory, request guards, error handling, health route
  auth.py                     Login, logout, and safe next-url handling
  config.py                   Environment-driven configuration
  extensions.py               Flask-SQLAlchemy instance
  models.py                   SQLAlchemy models and relationships
  routes.py                   Application pages, mutations, and export routes
  services/
    export.py                 JSON and Letterboxd CSV export builders
    metadata.py               TMDb metadata enrichment helpers
    statistics.py             Aggregated statistics
    tmdb.py                   TMDb API client
  static/
    css/styles.css            Responsive UI styling
    js/app.js                 Theme toggle, confirmations, mobile menu behavior
    img/                      Logo, favicon, SVG source icon, PNG app icons
    manifest.webmanifest      Home Screen / install metadata
  templates/
    _app_icons.html           Shared favicon, manifest, and iOS icon tags
    *.html                    Jinja2 pages, layout, macros, and errors
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
TRACKY_CREATE_SCHEMA_ON_STARTUP=false
```

`DATABASE_URL` can also be a local SQLite URL for development, for example `sqlite:///instance/tracky.sqlite3`. For Vercel production, use a persistent external database such as Neon Postgres.

`TRACKY_CREATE_SCHEMA_ON_STARTUP` defaults to `true` for SQLite and `false` for Postgres. Keep it `false` on Vercel because the persistent database is initialized once with `scripts/load_initial_database.py`.

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

When pointing local development at Neon/Postgres, keep `TRACKY_CREATE_SCHEMA_ON_STARTUP=false` so app startup does not run schema creation checks on every launch.

## iPhone Home Screen

Tracky includes the metadata Safari needs when using Share -> Add to Home Screen on iPhone:

- `apple-touch-icon` points to `tracky/static/img/app-icon-180.png`.
- `manifest.webmanifest` references the `192x192` and `512x512` PNG icons.
- The app title is set to `Tracky`.
- The manifest uses `display: standalone` and starts at `/`.

If an older Home Screen shortcut was created before these assets existed, remove that shortcut and add Tracky again from Safari so iOS refreshes the cached icon.

## Initial Database Load

The historical SQLite database is local bootstrap data only. It is not required by the Flask app at runtime.

Run the one-time load from your local machine, pointing the source to your local SQLite file and the target to the persistent database:

```bash
DATABASE_URL='postgresql://user:password@host/database?sslmode=require' \
python scripts/load_initial_database.py --source-url sqlite:///data/tracky.seed.sqlite3
```

The script creates the Tracky schema, copies the existing media data, preserves settings, and creates the configured `APP_USERNAME` user if needed. It refuses to copy into a database that already contains Tracky data. Use `--force` only when you intentionally want to replace the target data tables.

After the persistent database has been populated, keep `data/tracky.seed.sqlite3` local only. It should not be deployed or committed.

## Vercel Deployment

The project includes:

- `api/index.py`
- `vercel.json`
- `requirements.txt`

Set the same environment variables in Vercel project settings. The default Vercel Python entry point imports the Flask app from `tracky.create_app()`.

Use a persistent external `DATABASE_URL` in Vercel. A writable SQLite file inside a Vercel serverless function is not a permanent library.

Future corrections can be made from Search or the item edit form. They are permanent when `DATABASE_URL` points to the persistent database.

## Testing

```bash
pytest
```

The suite covers:

- Authentication and safe redirect behavior.
- Home Screen icon metadata and manifest references.
- TMDb client mapping.
- SQLAlchemy model relationships.
- Local search by Italian and original title.
- Favorites filtering.
- Alphabetical sorting.
- Statistics aggregation.
- Full JSON export.
- Letterboxd CSV export.

## Future Improvements

- Import from JSON backups.
- Import from Letterboxd exports.
- Background TMDb enrichment jobs for very large libraries.
- Advanced charts with a small progressive-enhancement JavaScript layer.
- CSV or JSON backup scheduling for production databases.
