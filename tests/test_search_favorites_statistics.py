from __future__ import annotations

from datetime import date, datetime

from tracky.extensions import db
from tracky.models import MediaItem, WatchEvent
from tracky.services.statistics import build_statistics
from tests.conftest import extract_csrf


def seed_items(app):
    with app.app_context():
        movie_a = MediaItem(
            media_type="movie",
            italian_title="A Movie",
            original_title="Alpha",
            watched_date=date(2024, 1, 2),
            favorite=True,
            personal_rating=8,
            tmdb_rating=7.5,
        )
        movie_z = MediaItem(
            media_type="movie",
            italian_title="Z Movie",
            original_title="Zeta",
            watched_date=date(2023, 1, 2),
            favorite=False,
            personal_rating=6,
            tmdb_rating=6.5,
        )
        show = MediaItem(
            media_type="tv",
            italian_title="Beta Show",
            original_title="Original Beta",
            watched_date=date(2022, 5, 8),
            favorite=True,
        )
        db.session.add_all([movie_z, show, movie_a])
        db.session.flush()
        db.session.add_all(
            [
                WatchEvent(media_item=movie_a, watched_at=datetime(2024, 1, 2, 20, 0), source="manual"),
                WatchEvent(media_item=movie_z, watched_at=datetime(2023, 1, 2, 20, 0), source="manual"),
            ]
        )
        db.session.commit()


def test_search_uses_italian_and_original_titles(app, client, login):
    seed_items(app)

    response = client.get("/search?q=Original+Beta")
    assert response.status_code == 200
    assert b"Beta Show" in response.data


def test_favorites_page_only_contains_favorites(app, client, login):
    seed_items(app)

    response = client.get("/favorites")
    assert b"A Movie" in response.data
    assert b"Beta Show" in response.data
    assert b"Z Movie" not in response.data


def test_library_is_sorted_by_italian_title(app, client, login):
    seed_items(app)

    response = client.get("/library")
    body = response.data.decode()
    assert body.index("A Movie") < body.index("Beta Show") < body.index("Z Movie")


def test_statistics_counts_watched_media(app):
    seed_items(app)

    with app.app_context():
        stats = build_statistics()

    assert stats["total_movies"] == 2
    assert stats["total_shows"] == 1
    assert stats["favorites_count"] == 2
    assert stats["average_personal_rating"] == 7.0


def test_metadata_batch_enrichment_updates_missing_tmdb_fields(app, client, login, monkeypatch):
    seed_items(app)

    class FakeTMDbClient:
        configured = True

        def find_by_imdb(self, imdb_id, expected_type):
            return 101

        def best_match(self, title, year, media_type):
            return 101

        def details(self, tmdb_id, media_type):
            return {
                "tmdb_id": tmdb_id,
                "imdb_id": "tt101",
                "italian_title": "A Movie Enriched",
                "original_title": "Alpha",
                "overview": "A richer overview.",
                "genres": ["Drama"],
                "primary_people": [{"name": "Director One", "tmdb_id": 1}],
                "cast": [{"name": "Actor One", "tmdb_id": 2}],
                "date": "2024-01-01",
                "tmdb_rating": 8.2,
                "tmdb_vote_count": 1200,
                "poster_path": "/poster.jpg",
                "backdrop_path": "/backdrop.jpg",
            }

    import tracky.routes

    monkeypatch.setattr(tracky.routes, "_tmdb_client", lambda: FakeTMDbClient())

    response = client.get("/metadata")
    token = extract_csrf(response.data)
    response = client.post(
        "/metadata/enrich",
        data={"_csrf_token": token, "batch_size": "1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"1 enriched" in response.data

    with app.app_context():
        item = MediaItem.query.filter_by(tmdb_id=101).one()
        assert item.italian_title == "A Movie Enriched"
        assert item.poster_path == "/poster.jpg"
        assert item.tmdb_rating == 8.2
        assert [genre.name for genre in item.genres] == ["Drama"]
