from __future__ import annotations

import re
from typing import Dict, Optional

from .playlist_importer import ImportedTrack, playlist_payload


SPOTIFY_URL_RE = re.compile(r"(?:open\.spotify\.com/(playlist|album)/|spotify:(playlist|album):)([A-Za-z0-9]+)")


def parse_spotify_playlist_id(url: str) -> Optional[str]:
    parsed = parse_spotify_url(url)
    return parsed[1] if parsed and parsed[0] == "playlist" else None


def parse_spotify_url(url: str) -> Optional[tuple[str, str]]:
    m = SPOTIFY_URL_RE.search(url or "")
    if not m:
        return None
    kind = m.group(1) or m.group(2)
    return kind, m.group(3)


def _track_from_spotify_api(track: Dict, source: str, album_override: Optional[Dict] = None) -> ImportedTrack:
    album = album_override or track.get("album") or {}
    images = album.get("images") or []
    external = track.get("external_urls") or {}
    ids = track.get("external_ids") or {}
    return ImportedTrack(
        title=track.get("name", ""),
        artist=", ".join(a.get("name", "") for a in track.get("artists") or [] if a.get("name")),
        album=album.get("name", ""),
        duration_ms=int(track.get("duration_ms") or 0),
        url=external.get("spotify", ""),
        source=source,
        isrc=ids.get("isrc", ""),
        cover_art=images[0]["url"] if images else "",
        identifiers={"spotify_id": track.get("id", ""), "isrc": ids.get("isrc", "")},
    )


def fetch_spotify_playlist(spotify_service, url: str, limit: int) -> Dict:
    parsed = parse_spotify_url(url)
    if not parsed:
        raise ValueError("Invalid Spotify playlist or album URL")
    kind, item_id = parsed
    if kind == "album":
        return fetch_spotify_album(spotify_service, item_id, limit)

    playlist = spotify_service._call(spotify_service.client.playlist, item_id, fields="name,images,tracks(total,items(track),next)")
    name = playlist.get("name") or "Spotify playlist"
    images = playlist.get("images") or []
    cover_art = images[0].get("url", "") if images else ""
    total_tracks = (playlist.get("tracks") or {}).get("total")
    tracks = []
    page = playlist.get("tracks") or {}
    while page:
        for item in page.get("items") or []:
            track = item.get("track") or {}
            if not track or track.get("is_local"):
                continue
            tracks.append(_track_from_spotify_api(track, "spotify"))
            if len(tracks) >= limit:
                return playlist_payload(name, "spotify", tracks, limit, cover_art=cover_art, track_count=total_tracks)
        next_url = page.get("next")
        if not next_url or len(tracks) >= limit:
            break
        page = spotify_service._call(spotify_service.client.next, page)
    return playlist_payload(name, "spotify", tracks, limit, cover_art=cover_art, track_count=total_tracks)


def fetch_spotify_album(spotify_service, album_id: str, limit: int) -> Dict:
    album = spotify_service._call(spotify_service.client.album, album_id)
    name = album.get("name") or "Spotify album"
    images = album.get("images") or []
    cover_art = images[0].get("url", "") if images else ""
    total_tracks = album.get("total_tracks")
    tracks = []
    page = album.get("tracks") or {}
    while page:
        for track in page.get("items") or []:
            if not track:
                continue
            track["external_ids"] = track.get("external_ids") or {}
            tracks.append(_track_from_spotify_api(track, "spotify", album_override=album))
            if len(tracks) >= limit:
                return playlist_payload(name, "spotify", tracks, limit, cover_art=cover_art, track_count=total_tracks)
        next_url = page.get("next")
        if not next_url or len(tracks) >= limit:
            break
        page = spotify_service._call(spotify_service.client.next, page)
    return playlist_payload(name, "spotify", tracks, limit, cover_art=cover_art, track_count=total_tracks)
