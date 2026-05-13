from __future__ import annotations

from typing import Dict, List

import requests

from .playlist_importer import ImportedTrack, playlist_payload


METHODS = {
    "loved": "user.getLovedTracks",
    "top": "user.getTopTracks",
    "recent": "user.getRecentTracks",
}


def _as_list(value) -> List:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _lastfm_get(params: Dict) -> Dict:
    r = requests.get(
        "https://ws.audioscrobbler.com/2.0/",
        params=params,
        headers={"User-Agent": "Musikat/1.0"},
        timeout=15,
    )
    try:
        data = r.json()
    except ValueError:
        r.raise_for_status()
        return {}
    if data.get("error"):
        raise RuntimeError(data.get("message", "Last.fm request failed"))
    r.raise_for_status()
    return data


def fetch_lastfm_tracks(api_key: str, username: str, import_type: str, limit: int) -> Dict:
    if not api_key:
        raise ValueError("Last.fm API key is not configured")
    if import_type not in METHODS:
        raise ValueError("Invalid Last.fm import type")
    params = {
        "method": METHODS[import_type],
        "user": username,
        "api_key": api_key,
        "format": "json",
        "limit": limit,
    }
    data = _lastfm_get(params)
    root = data.get("lovedtracks") or data.get("toptracks") or data.get("recenttracks") or {}
    attrs = root.get("@attr") or {}
    total_tracks = attrs.get("total")
    tracks = []
    for item in _as_list(root.get("track")):
        artist = item.get("artist") or {}
        artist_name = ""
        if isinstance(artist, dict):
            artist_name = artist.get("name") or artist.get("#text") or ""
        else:
            artist_name = str(artist or "")
        images = item.get("image") or []
        cover = ""
        if images:
            cover = (images[-1] or {}).get("#text", "")
        tracks.append(
            ImportedTrack(
                title=item.get("name", ""),
                artist=artist_name,
                url=item.get("url", ""),
                source="lastfm",
                cover_art=cover,
            )
        )
    return playlist_payload(
        f"Last.fm {import_type} tracks for {username}",
        "lastfm",
        tracks,
        limit,
        track_count=int(total_tracks) if str(total_tracks or "").isdigit() else None,
    )
