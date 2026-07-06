from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tracky import create_app
from tracky.config import BASE_DIR, Config
from tracky.extensions import db
from tracky.models import MediaItem, Setting
from tracky.services.bootstrap import bootstrap_from_tvtime, enrich_missing_metadata, missing_metadata_count
from tracky.services.tmdb import TMDbClient
from tracky.utils import utc_now


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Tracky seed SQLite database.")
    parser.add_argument(
        "--output",
        default=str(BASE_DIR / "data" / "tracky.seed.sqlite3"),
        help="Destination SQLite database path.",
    )
    parser.add_argument(
        "--export-dir",
        default=str(BASE_DIR / "tvtime-export-2026-07-03"),
        help="TV Time export directory.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing seed database.")
    parser.add_argument("--skip-tmdb", action="store_true", help="Build the seed without TMDb enrichment.")
    parser.add_argument(
        "--require-tmdb",
        action="store_true",
        help="Fail if TMDB_API_KEY is missing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).resolve()
    if output_path.exists() and not args.force:
        print(f"Seed database already exists: {output_path}")
        print("Use --force to rebuild it.")
        return 1

    tmdb_api_key = os.getenv("TMDB_API_KEY")
    if args.require_tmdb and not tmdb_api_key:
        print("TMDB_API_KEY is required but not configured.")
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    seed_config = type(
        "SeedConfig",
        (Config,),
        {
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{output_path}",
            "TRACKY_AUTO_BOOTSTRAP": False,
            "TRACKY_ENRICH_ON_STARTUP": False,
            "TRACKY_USE_SEED_DATABASE": False,
            "TRACKY_EXPORT_DIR": str(Path(args.export_dir).resolve()),
        },
    )

    app = create_app(seed_config)
    with app.app_context():
        db.drop_all()
        db.create_all()

        import_report = bootstrap_from_tvtime(str(Path(args.export_dir).resolve()))
        enriched = 0
        if not args.skip_tmdb and tmdb_api_key:
            client = TMDbClient(tmdb_api_key, language=app.config.get("TRACKY_TMDB_LANGUAGE", "it-IT"))
            enriched = enrich_missing_metadata(client)
        elif not args.skip_tmdb:
            print("TMDB_API_KEY is not configured; seed will contain TV Time data only.")

        remaining = missing_metadata_count()
        Setting.set("seed_database_built_at", utc_now().isoformat())
        Setting.set("seed_database_media_count", str(MediaItem.query.count()))
        Setting.set("seed_database_tmdb_enriched_count", str(enriched))
        Setting.set("seed_database_tmdb_remaining_count", str(remaining))
        if remaining == 0:
            Setting.set("tmdb_enrichment_completed", "true")
            Setting.set("tmdb_enrichment_completed_at", utc_now().isoformat())
        db.session.commit()

        print(f"Seed database: {output_path}")
        print(f"Movies imported: {import_report.movies}")
        print(f"TV shows imported: {import_report.shows}")
        print(f"Episodes imported: {import_report.episodes}")
        print(f"Watch events imported: {import_report.watch_events}")
        print(f"Media items: {MediaItem.query.count()}")
        print(f"TMDb enriched: {enriched}")
        print(f"Items still missing metadata: {remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
