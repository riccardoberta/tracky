# Tracky

Tracky is a personal movie and TV show tracker built with Python, Flask, SQLAlchemy, SQLite, Jinja2, HTML, CSS, and minimal vanilla JavaScript. It imports a TV Time export once, enriches movies and shows with TMDb metadata in Italian when available, and gives one authenticated user a permanent media library with timeline, library, favorites, search, item details, editing, and statistics.

## Features

- Session-based authentication with credentials from configuration.
- No public registration.
- TV Time bootstrap from the bundled export files.
- Idempotent import of movies, series, lists, episodes, watch history, favorites, IMDb IDs, TVDB IDs, and TV Time UUIDs.
- TMDb enrichment by IMDb ID first, then title search.
- Editable metadata and personal fields after import.
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
  __init__.py                 App factory, error handling, CLI command
  auth.py                     Login and logout routes
  config.py                   Environment-driven configuration
  extensions.py               Flask-SQLAlchemy instance
  models.py                   SQLAlchemy models and relationships
  routes.py                   Application routes and forms
  services/
    bootstrap.py              TV Time import and TMDb enrichment
    statistics.py             Aggregated statistics
    tmdb.py                   TMDb API client
  static/                     CSS, JavaScript, logo, favicon, app icon
  templates/                  Jinja2 templates
tests/                        Automated tests
tvtime-export-2026-07-03/     Bootstrap export data
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
DATABASE_URL=sqlite:///instance/tracky.sqlite3
PERSONAL_SCORE_MIN=1
PERSONAL_SCORE_MAX=10
TRACKY_AUTO_BOOTSTRAP=true
TRACKY_ENRICH_ON_STARTUP=true
TRACKY_EXPORT_DIR=tvtime-export-2026-07-03
TRACKY_TMDB_LANGUAGE=it-IT
```

## TMDb API Key

Create a TMDb account and generate an API key from the TMDb developer settings. Tracky uses it to:

- Search movies and TV shows.
- Match bootstrap records by IMDb ID when possible.
- Fetch Italian localized titles and overviews.
- Fetch original titles, genres, directors or creators, cast, release dates, ratings, vote counts, posters, and backdrops.

If `TMDB_API_KEY` is missing, Tracky still imports the TV Time export and shows a friendly warning. Enrichment can be run later with:

```bash
flask --app run.py bootstrap
```

## Running Locally

```bash
flask --app run.py run --debug
```

Open `http://127.0.0.1:5000`.

On first execution, Tracky creates the SQLite database, imports the TV Time export, and enriches records through TMDb when the key is configured and `TRACKY_ENRICH_ON_STARTUP=true`.

## Bootstrap From TV Time

The application expects files matching these patterns in `TRACKY_EXPORT_DIR`:

```text
tvtime-movies*.json
tvtime-series*.json
tvtime-lists*.json
```

The bundled export is already in:

```text
tvtime-export-2026-07-03/
```

The import is idempotent. Running it more than once does not create duplicate media items, episodes, lists, or watch events.

## Building a Seed Database

For serverless deployments, you can build the initial SQLite database once during development and commit only that seed database:

```bash
TMDB_API_KEY=your-tmdb-api-key python scripts/build_seed_database.py --force --require-tmdb
```

The script writes:

```text
data/tracky.seed.sqlite3
```

It imports the TV Time export once, enriches imported records with TMDb once, and stores the resulting database as a deployable seed. After this succeeds, the TV Time export files are no longer needed at runtime.

On Vercel, use:

```env
TRACKY_AUTO_BOOTSTRAP=false
TRACKY_ENRICH_ON_STARTUP=false
TRACKY_USE_SEED_DATABASE=true
TRACKY_SEED_DATABASE_PATH=data/tracky.seed.sqlite3
DATABASE_URL=sqlite:////tmp/tracky.sqlite3
```

When the function starts, Tracky copies the committed seed database into `/tmp/tracky.sqlite3`. This makes the initial library available without shipping the raw TV Time export. The `/tmp` copy is still ephemeral, so edits made on Vercel are not permanent until you move to a durable SQLite-compatible database such as Turso/libSQL.

## Vercel Deployment

The project includes:

- `api/index.py`
- `vercel.json`
- `requirements.txt`

Set the same environment variables in Vercel project settings. The default Vercel Python entry point imports the Flask app from `tracky.create_app()`.

Important SQLite note: Vercel serverless storage is not designed as a durable writable filesystem. When `DATABASE_URL` is not set and `VERCEL` is present, Tracky uses `sqlite:////tmp/tracky.sqlite3` so the function can start, but that file is ephemeral. For a permanent personal library on Vercel, use a SQLite-compatible remote database such as Turso/libSQL. Also keep `TRACKY_ENRICH_ON_STARTUP=false` on Vercel; TMDb search and manual imports still work, but long enrichment jobs should not run during serverless startup.

After the first Vercel deployment, sign in and open `Metadata`. Use `Enrich next batch` repeatedly to fill posters, ratings, genres, cast, and backdrops from TMDb in small serverless-safe batches.

## Testing

```bash
pytest
```

The suite covers:

- Authentication.
- TMDb client mapping.
- SQLAlchemy model relationships.
- Idempotent TV Time bootstrap.
- Local search by Italian and original title.
- Favorites filtering.
- Alphabetical sorting.
- Statistics aggregation.

## Future Improvements

- Episode-level editing in the UI.
- CSV or JSON export from the local library.
- Background TMDb enrichment jobs for very large libraries.
- Advanced charts with a small progressive-enhancement JavaScript layer.
- Optional external persistent database adapter for serverless hosting.
