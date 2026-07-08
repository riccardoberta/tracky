from __future__ import annotations

from datetime import date, datetime

from tracky.extensions import db
from tracky.models import MediaItem, Setting, WatchEvent
from tracky.services.statistics import build_statistics
from tracky.services.tmdb import TMDbSearchResult
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


def test_search_tmdb_add_form_defaults_watched_date_to_today(app, client, login, monkeypatch):
    class FakeTMDbClient:
        configured = True

        def search(self, query, media_type=None):
            return [
                TMDbSearchResult(
                    tmdb_id=123,
                    media_type="movie",
                    title="Remote Movie",
                    original_title="Remote Movie",
                    overview="Remote overview.",
                    poster_path=None,
                    date="2024-01-01",
                    vote_average=7.4,
                )
            ]

    import tracky.routes

    monkeypatch.setattr(tracky.routes, "_tmdb_client", lambda: FakeTMDbClient())
    monkeypatch.setattr(tracky.routes, "utc_now", lambda: datetime(2026, 7, 7, 12, 0))

    response = client.get("/search?q=Remote")

    assert response.status_code == 200
    assert b'name="watched_date" value="2026-07-07"' in response.data
    assert b'name="personal_rating"' in response.data
    assert b'value="6"' in response.data


def test_tmdb_import_saves_personal_rating(app, client, login, monkeypatch):
    class FakeTMDbClient:
        configured = True

        def search(self, query, media_type=None):
            return []

        def details(self, tmdb_id, media_type):
            return {
                "tmdb_id": tmdb_id,
                "imdb_id": "tt123",
                "italian_title": "Imported Movie",
                "original_title": "Imported Movie",
                "overview": "Imported overview.",
                "genres": ["Drama"],
                "primary_people": [{"name": "Director One", "tmdb_id": 1}],
                "cast": [{"name": "Actor One", "tmdb_id": 2}],
                "date": "2024-01-01",
                "tmdb_rating": 7.4,
                "tmdb_vote_count": 100,
                "poster_path": "/poster.jpg",
                "backdrop_path": "/backdrop.jpg",
            }

    import tracky.routes

    monkeypatch.setattr(tracky.routes, "_tmdb_client", lambda: FakeTMDbClient())

    response = client.get("/search?q=Imported")
    token = extract_csrf(response.data)
    response = client.post(
        "/media/import",
        data={
            "_csrf_token": token,
            "tmdb_id": "123",
            "media_type": "movie",
            "watched_date": "2026-07-07",
            "personal_rating": "6",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        item = MediaItem.query.filter_by(tmdb_id=123).one()
        assert item.personal_rating == 6


def test_detail_links_to_tmdb_when_item_has_tmdb_id(app, client, login):
    with app.app_context():
        item = MediaItem(media_type="tv", italian_title="Linked Show", tmdb_id=456)
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    response = client.get(f"/media/{item_id}")

    assert response.status_code == 200
    assert b"https://www.themoviedb.org/tv/456" in response.data
    assert b"Open on TMDb" in response.data


def test_check_page_saves_score_and_moves_to_next_item(app, client, login):
    seed_items(app)

    response = client.get("/check", follow_redirects=True)
    assert response.status_code == 200
    assert b"Check" in response.data
    assert b"A Movie" in response.data
    assert b"Previous" in response.data
    token = extract_csrf(response.data)

    with app.app_context():
        item = MediaItem.query.filter_by(italian_title="A Movie").one()
        item_id = item.id

    response = client.post(
        f"/check/{item_id}/ok",
        data={"_csrf_token": token, "personal_rating": "9"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Beta Show" in response.data
    with app.app_context():
        item = db.session.get(MediaItem, item_id)
        assert item.personal_rating == 9
        assert Setting.get(f"seed_review_item:{item_id}") is not None


def test_check_correction_updates_item_from_tmdb(app, client, login, monkeypatch):
    seed_items(app)

    class FakeTMDbClient:
        configured = True

        def details(self, tmdb_id, media_type):
            return {
                "tmdb_id": tmdb_id,
                "imdb_id": "tt999",
                "italian_title": "Correct Movie",
                "original_title": "Correct Original",
                "overview": "Correct overview.",
                "genres": ["Drama"],
                "primary_people": [{"name": "Director One", "tmdb_id": 1}],
                "cast": [{"name": "Actor One", "tmdb_id": 2}],
                "date": "2024-01-01",
                "tmdb_rating": 8.4,
                "tmdb_vote_count": 900,
                "poster_path": "/correct.jpg",
                "backdrop_path": "/correct-backdrop.jpg",
            }

    import tracky.routes

    monkeypatch.setattr(tracky.routes, "_tmdb_client", lambda: FakeTMDbClient())

    response = client.get("/check", follow_redirects=True)
    token = extract_csrf(response.data)
    with app.app_context():
        item = MediaItem.query.filter_by(italian_title="A Movie").one()
        item_id = item.id

    response = client.post(
        f"/check/{item_id}/correct",
        data={
            "_csrf_token": token,
            "personal_rating": "8",
            "tmdb_url": "https://www.themoviedb.org/movie/999",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        item = db.session.get(MediaItem, item_id)
        assert item.italian_title == "Correct Movie"
        assert item.tmdb_id == 999
        assert item.personal_rating == 8
        assert item.poster_path == "/correct.jpg"


def test_check_delete_removes_item_and_moves_to_neighbor(app, client, login):
    seed_items(app)

    response = client.get("/check", follow_redirects=True)
    token = extract_csrf(response.data)
    with app.app_context():
        item = MediaItem.query.filter_by(italian_title="A Movie").one()
        item_id = item.id
        Setting.set(f"seed_review_item:{item_id}", "ok:2026-07-07T00:00:00")
        db.session.commit()

    response = client.post(
        f"/check/{item_id}/delete",
        data={"_csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Beta Show" in response.data
    with app.app_context():
        assert db.session.get(MediaItem, item_id) is None
        assert Setting.get(f"seed_review_item:{item_id}") is None


def test_edit_can_return_to_check_after_saving(app, client, login):
    seed_items(app)

    with app.app_context():
        item = MediaItem.query.filter_by(italian_title="A Movie").one()
        item_id = item.id

    response = client.get(f"/media/{item_id}/edit?next=/check/{item_id}")
    token = extract_csrf(response.data)
    response = client.post(
        f"/media/{item_id}/edit",
        data={
            "_csrf_token": token,
            "next": f"/check/{item_id}",
            "italian_title": "A Movie Edited",
            "original_title": "Alpha",
            "release_date": "2024-01-01",
            "genres": "Drama",
            "primary_people": "Director One",
            "cast": "Actor One",
            "tmdb_rating": "7.5",
            "tmdb_vote_count": "20",
            "poster_path": "/poster.jpg",
            "backdrop_path": "/backdrop.jpg",
            "overview": "Edited overview.",
            "watched_date": "2024-01-02",
            "personal_rating": "9",
            "favorite": "1",
            "personal_notes": "Edited note.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"A Movie Edited" in response.data
    assert b"Check" in response.data
    with app.app_context():
        item = db.session.get(MediaItem, item_id)
        assert item.italian_title == "A Movie Edited"
        assert item.personal_rating == 9
        assert item.personal_notes == "Edited note."


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
