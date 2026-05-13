from __future__ import annotations

import re
from typing import Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

import requests

from .playlist_importer import ImportedTrack, playlist_payload


DEEZER_PLAYLIST_RE = re.compile(r"(?:deezer\.com/(?:[a-z]{2}/)?playlist/|deezer:playlist:)(\d+)", re.I)


def parse_deezer_playlist_id(url: str) -> Optional[str]:
    raw = url or ""
    m = DEEZER_PLAYLIST_RE.search(raw)
    if m:
        return m.group(1)

    parsed = urlparse(raw)
    query = parse_qs(parsed.query)
    for key in ("dest", "awf", "gwf", "iwf"):
        for value in query.get(key, []):
            m = DEEZER_PLAYLIST_RE.search(unquote(value))
            if m:
                return m.group(1)
    return None


def resolve_deezer_playlist_id(url: str) -> Optional[str]:
    playlist_id = parse_deezer_playlist_id(url)
    if playlist_id:
        return playlist_id
    host = (urlparse(url or "").hostname or "").lower()
    if host != "link.deezer.com":
        return None
    r = requests.get(url, allow_redirects=False, timeout=15)
    r.raise_for_status()
    location = r.headers.get("location") or ""
    playlist_id = parse_deezer_playlist_id(location)
    if playlist_id:
        return playlist_id
    # Some share pages may require one more hop; keep it bounded.
    if location:
        r2 = requests.get(location, allow_redirects=False, timeout=15)
        r2.raise_for_status()
        return parse_deezer_playlist_id(r2.headers.get("location") or r2.url)
    return None


def fetch_deezer_playlist(url: str, limit: int) -> Dict:
    playlist_id = resolve_deezer_playlist_id(url)
    if not playlist_id:
        raise ValueError("Invalid Deezer playlist URL")
    r = requests.get(f"https://api.deezer.com/playlist/{playlist_id}", timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(data["error"].get("message", "Deezer playlist request failed"))
    tracks = []
    cover_art = data.get("picture_xl") or data.get("picture_big") or data.get("picture_medium") or ""
    total_tracks = data.get("nb_tracks")
    total_duration = int(data.get("duration") or 0) * 1000 if data.get("duration") else None
    track_page = data.get("tracks") or {}
    items = track_page.get("data") or []
    next_url = track_page.get("next")
    while items and len(tracks) < limit:
        item = items.pop(0)
        artist = item.get("artist") or {}
        album = item.get("album") or {}
        tracks.append(
            ImportedTrack(
                title=item.get("title", ""),
                artist=artist.get("name", ""),
                album=album.get("title", ""),
                duration_ms=int(item.get("duration") or 0) * 1000,
                url=item.get("link", ""),
                source="deezer",
                cover_art=album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium") or "",
                identifiers={"deezer_id": str(item.get("id", ""))},
            )
        )
        if not items and next_url and len(tracks) < limit:
            page = requests.get(next_url, timeout=15)
            page.raise_for_status()
            page_data = page.json()
            items = page_data.get("data") or []
            next_url = page_data.get("next")
    return playlist_payload(
        data.get("title") or "Deezer playlist",
        "deezer",
        tracks,
        limit,
        cover_art=cover_art,
        track_count=total_tracks,
        duration_ms=total_duration,
    )
