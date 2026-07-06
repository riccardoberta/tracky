from __future__ import annotations

import json
import sqlite3

from tracky.extensions import db
from tracky import create_app
from tracky.models import Episode, MediaItem, MediaList, Setting, WatchEvent
from tracky.services.bootstrap import bootstrap_from_tvtime, enrich_metadata_batch, missing_metadata_count
from tests.conftest import TestConfig


def test_tvtime_bootstrap_is_idempotent(app, tmp_path):
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    (export_dir / "tvtime-movies.json").write_text(
        json.dumps(
            [
                {
                    "id": {"tvdb": 10, "imdb": "tt001"},
                    "uuid": "movie-uuid",
                    "created_at": "2024-01-02T20:00:00Z",
                    "title": "Original Movie",
                    "year": 2024,
                    "watched_at": "2024-01-02T20:00:00Z",
                    "is_watched": True,
                    "is_favorite": True,
                    "rewatch_count": 0,
                }
            ]
        ),
        encoding="utf-8",
    )
    (export_dir / "tvtime-series.json").write_text(
        json.dumps(
            [
                {
                    "uuid": "show-uuid",
                    "id": {"tvdb": 20, "imdb": None},
                    "created_at": "2023-01-01T10:00:00Z",
                    "title": "A Show",
                    "is_favorite": False,
                    "seasons": [
                        {
                            "number": 1,
                            "is_specials": False,
                            "episodes": [
                                {
                                    "id": {"tvdb": 201, "imdb": None},
                                    "number": 1,
                                    "name": "Pilot",
                                    "special": False,
                                    "is_watched": True,
                                    "watched_at": "2023-03-04 21:30:00",
                                    "rewatch_count": 0,
                                    "watched_count": 1,
                                }
                            ],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    (export_dir / "tvtime-lists.json").write_text(
        json.dumps(
            [
                {
                    "id": "list-1",
                    "name": "Watchlist",
                    "description": "",
                    "is_public": False,
                    "created_at": "2025-01-01T00:00:00Z",
                    "items": [{"type": "movie", "uuid": "movie-uuid", "name": "Original Movie", "custom_order": 0}],
                }
            ]
        ),
        encoding="utf-8",
    )

    with app.app_context():
        first = bootstrap_from_tvtime(str(export_dir))
        second = bootstrap_from_tvtime(str(export_dir))

        assert first.movies == 1
        assert first.shows == 1
        assert second.movies == 0
        assert second.shows == 0
        assert MediaItem.query.count() == 2
        assert Episode.query.count() == 1
        assert WatchEvent.query.count() == 2
        assert MediaList.query.count() == 1

        movie = MediaItem.query.filter_by(media_type="movie").one()
        assert movie.favorite is True
        assert movie.watched_date.isoformat() == "2024-01-02"

        show = MediaItem.query.filter_by(media_type="tv").one()
        assert show.watched_date.isoformat() == "2023-03-04"
        db.session.rollback()


def test_seed_database_is_copied_to_runtime_sqlite_path(tmp_path):
    seed_path = tmp_path / "tracky.seed.sqlite3"
    runtime_path = tmp_path / "runtime.sqlite3"

    connection = sqlite3.connect(seed_path)
    connection.execute(
        "CREATE TABLE settings (key VARCHAR(120) PRIMARY KEY, value TEXT, updated_at DATETIME NOT NULL)"
    )
    connection.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        ("seed_marker", "copied", "2026-01-01 00:00:00"),
    )
    connection.commit()
    connection.close()

    class RuntimeConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{runtime_path}"
        TRACKY_AUTO_BOOTSTRAP = False
        TRACKY_USE_SEED_DATABASE = True
        TRACKY_SEED_DATABASE_PATH = str(seed_path)

    app = create_app(RuntimeConfig)

    assert runtime_path.exists()
    with app.app_context():
        assert Setting.get("seed_marker") == "copied"


def test_tmdb_enrichment_handles_duplicate_tmdb_matches(app):
    class DuplicateTMDbClient:
        configured = True

        def find_by_imdb(self, imdb_id, expected_type):
            return 500

        def best_match(self, title, year, media_type):
            return 500

        def details(self, tmdb_id, media_type):
            return {
                "tmdb_id": tmdb_id,
                "imdb_id": "tt500",
                "italian_title": "Shared Match",
                "original_title": "Shared Match",
                "overview": "Metadata copied from TMDb.",
                "genres": ["Drama"],
                "primary_people": [{"name": "Director One", "tmdb_id": 1}],
                "cast": [{"name": "Actor One", "tmdb_id": 2}],
                "date": "2020-01-01",
                "tmdb_rating": 7.1,
                "tmdb_vote_count": 100,
                "poster_path": "/poster.jpg",
                "backdrop_path": "/backdrop.jpg",
            }

    with app.app_context():
        db.session.add_all(
            [
                MediaItem(media_type="movie", italian_title="Local A", original_title="Local A"),
                MediaItem(media_type="movie", italian_title="Local B", original_title="Local B"),
            ]
        )
        db.session.commit()

        report = enrich_metadata_batch(DuplicateTMDbClient(), limit=2)

        assert report.enriched == 2
        assert missing_metadata_count() == 0
        assert MediaItem.query.filter_by(tmdb_id=500).count() == 1
        assert MediaItem.query.filter_by(poster_path="/poster.jpg").count() == 2
