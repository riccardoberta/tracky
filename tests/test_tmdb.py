from __future__ import annotations

from tracky.services.tmdb import TMDbClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        if "/find/" in url:
            return FakeResponse({"movie_results": [{"id": 123}], "tv_results": []})
        if "/movie/123" in url:
            return FakeResponse(
                {
                    "id": 123,
                    "title": "Titolo italiano",
                    "original_title": "Original Title",
                    "overview": "Overview",
                    "genres": [{"name": "Drama"}],
                    "release_date": "2024-05-01",
                    "vote_average": 7.8,
                    "vote_count": 450,
                    "poster_path": "/poster.jpg",
                    "backdrop_path": "/backdrop.jpg",
                    "external_ids": {"imdb_id": "tt001"},
                    "credits": {
                        "crew": [{"job": "Director", "name": "Director One", "id": 7}],
                        "cast": [{"name": "Actor One", "id": 8}],
                    },
                }
            )
        return FakeResponse({"results": []})


def test_tmdb_client_finds_and_maps_movie_details():
    session = FakeSession()
    client = TMDbClient("api-key", session=session)

    assert client.find_by_imdb("tt001", "movie") == 123
    details = client.details(123, "movie")

    assert details["italian_title"] == "Titolo italiano"
    assert details["original_title"] == "Original Title"
    assert details["genres"] == ["Drama"]
    assert details["primary_people"][0]["name"] == "Director One"
    assert details["cast"][0]["name"] == "Actor One"
    assert details["tmdb_rating"] == 7.8
