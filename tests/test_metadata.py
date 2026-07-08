from __future__ import annotations

from tracky import create_app
from tracky.extensions import db
from tracky.models import MediaItem, Setting
from tracky.services.metadata import enrich_metadata_batch, missing_metadata_count
from scripts.load_initial_database import load_initial_database
from tests.conftest import TestConfig


def test_initial_database_loader_copies_local_sqlite_to_target(tmp_path, monkeypatch):
    source_path = tmp_path / "source.sqlite3"
    target_path = tmp_path / "target.sqlite3"

    class SourceConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{source_path}"

    source_app = create_app(SourceConfig)
    with source_app.app_context():
        db.session.add(MediaItem(media_type="movie", italian_title="Seed Movie", source="seed"))
        Setting.set("initial_load_marker", "copied")
        db.session.commit()
        db.session.remove()

    monkeypatch.setenv("APP_USERNAME", "owner")
    summary = load_initial_database(
        f"sqlite:///{source_path}",
        f"sqlite:///{target_path}",
    )

    class TargetConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{target_path}"

    target_app = create_app(TargetConfig)
    with target_app.app_context():
        assert summary.copied_rows["media_items"] == 1
        assert MediaItem.query.filter_by(italian_title="Seed Movie").count() == 1
        assert Setting.get("initial_load_marker") == "copied"


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
