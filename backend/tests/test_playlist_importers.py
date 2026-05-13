from __future__ import annotations

import pytest

from services.csv_importer import parse_csv_playlist
from services.deezer_playlist import fetch_deezer_playlist, parse_deezer_playlist_id, resolve_deezer_playlist_id
from services.lastfm_service import fetch_lastfm_tracks
from services.listenbrainz_service import fetch_listenbrainz_playlists, fetch_listenbrainz_tracks
from services.m3u_importer import parse_m3u_playlist
from services.playlist_importer import ImportedTrack, dedupe_tracks, match_tracks, playlist_payload
from services.spotify_playlist import parse_spotify_playlist_id, parse_spotify_url
from services.spotify_web_playlist import parse_spotify_embed_playlist


def test_csv_parsing_maps_common_columns() -> None:
    data = "Song,Artist Name,Album,Duration,URL\nMidnight,Jess,Blue,3:05,https://x\n"
    tracks = parse_csv_playlist(data)
    assert len(tracks) == 1
    assert tracks[0].title == "Midnight"
    assert tracks[0].artist == "Jess"
    assert tracks[0].album == "Blue"
    assert tracks[0].duration_ms == 185000


def test_csv_parsing_handles_malformed_empty_file() -> None:
    assert parse_csv_playlist("") == []


def test_m3u_parses_extinf_and_paths() -> None:
    data = """#EXTM3U
#EXTINF:245,Artist One - First Song
/music/Artist One/Album/01 First Song.mp3
/music/Artist Two/Second Album/Second Song.flac
"""
    tracks = parse_m3u_playlist(data)
    assert len(tracks) == 2
    assert tracks[0].artist == "Artist One"
    assert tracks[0].title == "First Song"
    assert tracks[0].duration_ms == 245000
    assert tracks[1].artist == "Artist Two"
    assert tracks[1].album == "Second Album"
    assert tracks[1].title == "Second Song"


def test_playlist_url_parsers() -> None:
    assert parse_spotify_playlist_id("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=x") == "37i9dQZF1DXcBWIGoYBM5M"
    assert parse_spotify_playlist_id("spotify:playlist:abc123") == "abc123"
    assert parse_spotify_url("https://open.spotify.com/album/5pF05wJrbrIvqunE41vWP8?si=x") == ("album", "5pF05wJrbrIvqunE41vWP8")
    assert parse_deezer_playlist_id("https://www.deezer.com/us/playlist/123456") == "123456"
    assert parse_deezer_playlist_id("https://link.deezer.com/?dest=https%3A%2F%2Fwww.deezer.com%2Fplaylist%2F15230519563%3Futm_source%3Dshare") == "15230519563"
    assert parse_deezer_playlist_id("not a playlist") is None


def test_spotify_web_embed_parsing() -> None:
    html = """
    <script id="__NEXT_DATA__" type="application/json">{
      "props": {"pageProps": {"state": {"data": {"entity": {
        "name": "Web Mix",
        "coverArt": {"sources": [{"url": "cover"}]},
        "trackList": [
          {"uri": "spotify:track:abc", "title": "Song", "subtitle": "Artist,&nbsp;Other", "duration": 123000}
        ]
      }}}}}
    }</script>
    """
    payload = parse_spotify_embed_playlist(html, 10)
    assert payload["playlist"]["name"] == "Web Mix"
    assert payload["playlist"]["source"] == "spotify_web"
    assert payload["playlist"]["cover_art"] == "cover"
    assert payload["playlist"]["duration_ms"] == 123000
    assert payload["tracks"][0]["title"] == "Song"
    assert payload["tracks"][0]["artist"] == "Artist, Other"
    assert payload["tracks"][0]["identifiers"]["spotify_id"] == "abc"


def test_deezer_short_link_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        headers = {
            "location": "https://link.deezer.com/?dest=https%3A%2F%2Fwww.deezer.com%2Fplaylist%2F15230519563%3Futm_source%3Dshare"
        }

        def raise_for_status(self):
            pass

    monkeypatch.setattr("services.deezer_playlist.requests.get", lambda *a, **k: Response())
    assert resolve_deezer_playlist_id("https://link.deezer.com/s/339mHCKmo1Bsf4v97iZHl") == "15230519563"


def test_match_tracks_marks_unmatched() -> None:
    class EmptyService:
        def search_tracks(self, query, limit=5):
            return []

    out = match_tracks([{"title": "Nope", "artist": "Nobody", "source": "csv"}], EmptyService())
    assert out[0]["match_status"] == "unmatched"
    assert out[0]["matched_track"] is None


def test_match_tracks_scores_good_candidate() -> None:
    class FakeService:
        def search_tracks(self, query, limit=5):
            return [{"id": "1", "name": "Song A", "artist": "Artist A", "album": "Album", "duration_ms": 100000}]

    out = match_tracks([{"title": "Song A", "artist": "Artist A", "album": "Album", "duration_ms": 100000}], FakeService())
    assert out[0]["match_status"] == "matched"
    assert out[0]["matched_track"]["id"] == "1"


def test_duplicate_tracks_are_removed() -> None:
    tracks = parse_csv_playlist("title,artist\nOne,A\nOne,A\nOne,B\n")
    deduped = dedupe_tracks(tracks)
    assert [(t.title, t.artist) for t in deduped] == [("One", "A"), ("One", "B")]


def test_playlist_payload_adds_summary_metadata() -> None:
    payload = playlist_payload(
        "Mix",
        "deezer",
        [
            ImportedTrack(title="One", artist="A", duration_ms=60000, cover_art="cover"),
            ImportedTrack(title="Two", artist="B", duration_ms=90000),
        ],
        10,
        track_count=25,
    )
    assert payload["playlist"]["track_count"] == 25
    assert payload["playlist"]["imported_track_count"] == 2
    assert payload["playlist"]["duration_ms"] == 150000
    assert payload["playlist"]["cover_art"] == "cover"


def test_deezer_response_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "title": "Mix",
                "nb_tracks": 1,
                "picture_medium": "playlist-cover",
                "duration": 10,
                "tracks": {
                    "data": [
                        {
                            "id": 1,
                            "title": "Track",
                            "duration": 10,
                            "artist": {"name": "Artist"},
                            "album": {"title": "Album", "cover_medium": "cover"},
                        }
                    ]
                },
            }

    monkeypatch.setattr("services.deezer_playlist.requests.get", lambda *a, **k: Response())
    payload = fetch_deezer_playlist("https://deezer.com/playlist/1", 10)
    assert payload["playlist"]["name"] == "Mix"
    assert payload["playlist"]["track_count"] == 1
    assert payload["playlist"]["cover_art"] == "playlist-cover"
    assert payload["playlist"]["duration_ms"] == 10000
    assert payload["tracks"][0]["artist"] == "Artist"


def test_lastfm_response_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"lovedtracks": {"@attr": {"total": "44"}, "track": [{"name": "Loved", "artist": {"name": "Artist"}}]}}

    monkeypatch.setattr("services.lastfm_service.requests.get", lambda *a, **k: Response())
    payload = fetch_lastfm_tracks("key", "user", "loved", 10)
    assert payload["playlist"]["track_count"] == 44
    assert payload["tracks"][0]["title"] == "Loved"
    assert payload["tracks"][0]["artist"] == "Artist"


def test_lastfm_missing_credentials() -> None:
    with pytest.raises(ValueError):
        fetch_lastfm_tracks("", "user", "loved", 10)


def test_lastfm_api_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def json(self):
            return {"error": 10, "message": "Invalid API key"}

        def raise_for_status(self):
            raise AssertionError("JSON Last.fm errors should be raised before HTTP errors")

    monkeypatch.setattr("services.lastfm_service.requests.get", lambda *a, **k: Response())
    with pytest.raises(RuntimeError, match="Invalid API key"):
        fetch_lastfm_tracks("bad-key", "user", "loved", 10)


def test_listenbrainz_response_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "payload": {
                    "listens": [
                        {
                            "track_metadata": {
                                "track_name": "Recent",
                                "artist_name": "Artist",
                                "release_name": "Album",
                            }
                        }
                    ]
                }
            }

    monkeypatch.setattr("services.listenbrainz_service.requests.get", lambda *a, **k: Response())
    payload = fetch_listenbrainz_tracks("user", "recent", 10)
    assert payload["tracks"][0]["title"] == "Recent"
    assert payload["tracks"][0]["album"] == "Album"


def test_listenbrainz_playlist_list_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "payload": {
                    "playlists": [
                        {
                            "playlist": {
                                "title": "Road songs",
                                "identifier": ["https://listenbrainz.org/playlist/playlist-mbid"],
                            }
                        }
                    ]
                }
            }

    monkeypatch.setattr("services.listenbrainz_service.requests.get", lambda *a, **k: Response())
    playlists = fetch_listenbrainz_playlists("user", 10)
    assert playlists == [{"id": "playlist-mbid", "title": "Road songs", "track_count": 0}]


def test_listenbrainz_specific_playlist_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "playlist": {
                        "title": "Road songs",
                        "image": "playlist-cover",
                        "track": [
                        {
                            "title": "Playlist Track",
                            "creator": "Playlist Artist",
                            "album": "Playlist Album",
                            "identifier": ["https://musicbrainz.org/recording/recording-mbid"],
                        }
                    ],
                }
            }

    monkeypatch.setattr("services.listenbrainz_service.requests.get", lambda *a, **k: Response())
    payload = fetch_listenbrainz_tracks("user", "playlist:playlist-mbid", 10)
    assert payload["playlist"]["name"] == "Road songs"
    assert payload["playlist"]["cover_art"] == "playlist-cover"
    assert payload["playlist"]["track_count"] == 1
    assert payload["tracks"][0]["title"] == "Playlist Track"
    assert payload["tracks"][0]["artist"] == "Playlist Artist"
    assert payload["tracks"][0]["identifiers"]["recording_mbid"] == "recording-mbid"


def test_listenbrainz_jspf_wrapped_playlist_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "jspf": {
                    "playlist": {
                        "title": "Wrapped",
                        "track": [{"title": "Wrapped Track", "creator": "Wrapped Artist"}],
                    }
                }
            }

    monkeypatch.setattr("services.listenbrainz_service.requests.get", lambda *a, **k: Response())
    payload = fetch_listenbrainz_tracks("user", "playlist:playlist-mbid", 10)
    assert payload["playlist"]["name"] == "Wrapped"
    assert payload["tracks"][0]["title"] == "Wrapped Track"
