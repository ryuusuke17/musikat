from __future__ import annotations

import html
import json
import re
from typing import Dict, Optional

import requests

from .playlist_importer import ImportedTrack, playlist_payload
from .spotify_playlist import parse_spotify_url


NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.S,
)


def _artist_names(subtitle: str) -> str:
    return " ".join((subtitle or "").replace("\xa0", " ").split())


def _track_id(uri: str) -> str:
    if not uri:
        return ""
    return uri.split(":")[-1] if uri.startswith("spotify:track:") else uri


def _cover_art(entity: Dict) -> str:
    cover = entity.get("coverArt") or {}
    sources = cover.get("sources") or []
    if sources:
        return sources[0].get("url", "")
    return cover.get("url", "") if isinstance(cover, dict) else ""


def _album_name(entity: Dict, item: Dict) -> str:
    return item.get("album") or item.get("albumName") or (entity.get("name") if entity.get("type") == "album" else "")


def parse_spotify_embed_playlist(html_text: str, limit: int) -> Dict:
    match = NEXT_DATA_RE.search(html_text or "")
    if not match:
        raise ValueError("Spotify web page did not include playlist data")
    data = json.loads(html.unescape(match.group(1)))
    entity = (
        data.get("props", {})
        .get("pageProps", {})
        .get("state", {})
        .get("data", {})
        .get("entity", {})
    )
    if not entity:
        raise ValueError("Spotify web playlist data was empty")

    playlist_name = entity.get("name") or entity.get("title") or "Spotify playlist"
    cover = _cover_art(entity)
    tracks = []
    for item in entity.get("trackList") or []:
        title = item.get("title") or ""
        if not title:
            continue
        uri = item.get("uri") or ""
        track_id = _track_id(uri)
        tracks.append(
            ImportedTrack(
                title=title,
                artist=_artist_names(item.get("subtitle", "")),
                album=_album_name(entity, item),
                duration_ms=int(item.get("duration") or 0),
                url=f"https://open.spotify.com/track/{track_id}" if track_id else "",
                source="spotify_web",
                cover_art=cover,
                identifiers={"spotify_id": track_id} if track_id else {},
            )
        )
        if len(tracks) >= limit:
            break
    total_tracks = entity.get("trackCount") or entity.get("track_count") or entity.get("totalTrackCount")
    return playlist_payload(
        playlist_name,
        "spotify_web",
        tracks,
        limit,
        cover_art=cover,
        track_count=total_tracks,
    )


def fetch_spotify_web_playlist(url: str, limit: int) -> Dict:
    parsed = parse_spotify_url(url)
    if not parsed:
        raise ValueError("Invalid Spotify playlist or album URL")
    kind, item_id = parsed
    embed_url = f"https://open.spotify.com/embed/{kind}/{item_id}"
    r = requests.get(
        embed_url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    r.raise_for_status()
    payload = parse_spotify_embed_playlist(r.text, limit)
    payload["playlist"]["source"] = "spotify_web"
    return payload
