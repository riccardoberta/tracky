from __future__ import annotations

import csv
import json
from datetime import date, datetime
from io import StringIO

from tracky.extensions import db
from tracky.models import Episode, MediaItem, MediaList, MediaListItem, Setting, WatchEvent


def test_export_json_requires_authentication(client):
    response = client.get("/export.json")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_letterboxd_export_requires_authentication(client):
    response = client.get("/export/letterboxd.csv")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_dashboard_links_to_json_export(client, login):
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b'href="/export.json"' in response.data
    assert b"Export JSON" in response.data
    assert b'href="/export/letterboxd.csv"' in response.data
    assert b"Export Letterboxd" in response.data


def test_export_json_contains_all_application_tables(app, client, login):
    with app.app_context():
        movie = MediaItem(
            media_type="movie",
            tmdb_id=100,
            imdb_id="tt0100",
            italian_title="Export Movie",
            original_title="Original Export Movie",
            overview="Stored overview.",
            release_date=date(2024, 4, 5),
            tmdb_rating=7.6,
            tmdb_vote_count=25,
            poster_path="/poster.jpg",
            backdrop_path="/backdrop.jpg",
            watched_date=date(2024, 4, 6),
            favorite=True,
            personal_rating=8,
            personal_notes="Worth exporting.",
            source="test",
        )
        db.session.add(movie)
        db.session.flush()
        movie.set_genres(["Drama"])
        movie.set_people("director", ["Director One"])
        episode = Episode(
            media_item=movie,
            season_number=1,
            episode_number=1,
            title="Pilot",
            is_watched=True,
            watched_at=datetime(2024, 4, 6, 20, 30),
            watched_count=1,
        )
        watch_event = WatchEvent(
            media_item=movie,
            episode=episode,
            watched_at=datetime(2024, 4, 6, 20, 30),
            source="manual",
            watch_count=1,
        )
        media_list = MediaList(name="Export List", description="A list to export.", is_public=False)
        db.session.add_all([episode, watch_event, media_list])
        db.session.flush()
        db.session.add(MediaListItem(media_list=media_list, media_item=movie, sort_order=1))
        Setting.set("export_marker", "included")
        db.session.commit()

    response = client.get("/export.json")

    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert response.headers["Content-Disposition"].startswith('attachment; filename="tracky-export-')
    assert response.headers["X-Content-Type-Options"] == "nosniff"

    payload = json.loads(response.data)
    assert payload["format"] == "tracky.export.v1"
    assert payload["counts"]["media_items"] == 1
    assert payload["counts"]["media_genres"] == 1
    assert payload["counts"]["media_people"] == 1
    assert payload["counts"]["episodes"] == 1
    assert payload["counts"]["watch_events"] == 1
    assert payload["counts"]["media_lists"] == 1
    assert payload["counts"]["media_list_items"] == 1

    assert payload["users"][0]["username"] == "owner"
    assert payload["media_items"][0]["italian_title"] == "Export Movie"
    assert payload["media_items"][0]["release_date"] == "2024-04-05"
    assert payload["genres"][0]["name"] == "Drama"
    assert payload["people"][0]["name"] == "Director One"
    assert payload["episodes"][0]["title"] == "Pilot"
    assert payload["watch_events"][0]["watched_at"] == "2024-04-06T20:30:00Z"
    assert payload["media_lists"][0]["name"] == "Export List"
    assert payload["settings"][0]["key"] == "export_marker"


def test_letterboxd_export_contains_movies_only(app, client, login):
    with app.app_context():
        movie = MediaItem(
            media_type="movie",
            tmdb_id=100,
            imdb_id="tt0100",
            italian_title="Film esportato",
            original_title="Exported Film",
            release_date=date(2024, 4, 5),
            watched_date=date(2024, 4, 6),
            personal_rating=8,
            personal_notes='Great "rewatch", worth it.',
            source="test",
        )
        tv_show = MediaItem(
            media_type="tv",
            tmdb_id=200,
            italian_title="Exported Show",
            first_air_date=date(2024, 1, 1),
            watched_date=date(2024, 1, 2),
            personal_rating=9,
        )
        db.session.add_all([movie, tv_show])
        db.session.flush()
        movie.set_people("director", ["Director One"])
        db.session.commit()

    response = client.get("/export/letterboxd.csv")

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.headers["Content-Disposition"].startswith('attachment; filename="tracky-letterboxd-')
    assert response.headers["X-Content-Type-Options"] == "nosniff"

    rows = list(csv.DictReader(StringIO(response.data.decode()), escapechar="\\", doublequote=False))
    assert len(rows) == 1
    assert rows[0] == {
        "tmdbID": "100",
        "imdbID": "tt0100",
        "Title": "Exported Film",
        "Year": "2024",
        "Directors": "Director One",
        "Rating": "4",
        "WatchedDate": "2024-04-06",
        "Rewatch": "",
        "Tags": "",
        "Review": 'Great "rewatch", worth it.',
    }
