from __future__ import annotations

from typing import Dict, List

import requests

from .playlist_importer import ImportedTrack, playlist_payload


BASE = "https://api.listenbrainz.org/1"


def _recording_to_track(item: Dict, source: str) -> ImportedTrack:
    info = item.get("track_metadata") or item.get("recording") or item
    if item.get("title") or item.get("creator") or item.get("album"):
        info = {
            **info,
            "track_name": item.get("title") or info.get("track_name") or info.get("title"),
            "artist_name": item.get("creator") or info.get("artist_name"),
            "release_name": item.get("album") or info.get("release_name"),
        }
    additional = info.get("additional_info") or {}
    duration_raw = additional.get("duration_ms") or additional.get("duration")
    try:
        duration_ms = int(duration_raw or 0)
    except (TypeError, ValueError):
        duration_ms = 0
    if duration_ms and duration_ms < 10_000:
        duration_ms *= 1000
    identifiers = item.get("identifier") or []
    recording_mbid = info.get("mbid") or additional.get("recording_mbid") or ""
    if not recording_mbid and identifiers:
        recording_mbid = str(identifiers[0]).rstrip("/").split("/")[-1]
    return ImportedTrack(
        title=info.get("track_name") or info.get("title") or "",
        artist=info.get("artist_name") or "",
        album=info.get("release_name") or additional.get("release_name") or "",
        duration_ms=duration_ms,
        source=source,
        identifiers={
            "recording_mbid": recording_mbid,
            "artist_mbid": additional.get("artist_mbids", [""])[0] if additional.get("artist_mbids") else "",
        },
        raw=item,
    )


def _payload(data: Dict) -> Dict:
    return data.get("payload") or data.get("jspf") or data


def _playlist_mbid_from_identifier(playlist: Dict) -> str:
    identifiers = playlist.get("identifier") or []
    for ident in identifiers:
        text = str(ident or "").rstrip("/")
        if text:
            return text.split("/")[-1]
    return playlist.get("playlist_mbid") or playlist.get("mbid") or playlist.get("id") or ""


def _playlist_title(playlist: Dict) -> str:
    return playlist.get("title") or playlist.get("name") or playlist.get("playlist_name") or "Untitled playlist"


def _playlist_object(data: Dict) -> Dict:
    payload = _payload(data)
    return payload.get("playlist") or payload.get("jspf", {}).get("playlist") or payload


def _playlist_tracks(playlist: Dict) -> List[Dict]:
    tracks = playlist.get("track")
    if tracks is None:
        tracks = playlist.get("tracks")
    return tracks or []


def _playlist_cover_art(playlist: Dict) -> str:
    image = playlist.get("image") or playlist.get("cover_art") or playlist.get("coverArt") or ""
    if isinstance(image, list):
        for item in reversed(image):
            if isinstance(item, dict) and item.get("#text"):
                return item.get("#text", "")
            if isinstance(item, str) and item:
                return item
        return ""
    if isinstance(image, dict):
        return image.get("url") or image.get("#text") or ""
    extension = playlist.get("extension") or {}
    if isinstance(extension, dict):
        return extension.get("https://musicbrainz.org/doc/jspf#cover_art") or extension.get("cover_art") or ""
    return str(image or "")


def fetch_listenbrainz_playlists(username: str, limit: int) -> List[Dict]:
    r = requests.get(f"{BASE}/user/{username}/playlists", params={"count": limit}, timeout=15)
    r.raise_for_status()
    data = _payload(r.json())
    playlists = []
    for item in data.get("playlists") or []:
        playlist = _playlist_object(item)
        mbid = _playlist_mbid_from_identifier(playlist)
        if not mbid:
            continue
        playlists.append(
            {
                "id": mbid,
                "title": _playlist_title(playlist),
                "track_count": len(_playlist_tracks(playlist)),
            }
        )
    return playlists


def fetch_listenbrainz_playlist(playlist_mbid: str, limit: int) -> Dict:
    r = requests.get(f"{BASE}/playlist/{playlist_mbid}", params={"fetch_metadata": "true"}, timeout=15)
    r.raise_for_status()
    playlist = _playlist_object(r.json())
    tracks = []
    for item in _playlist_tracks(playlist):
        tracks.append(_recording_to_track(item, "listenbrainz"))
        if len(tracks) >= limit:
            break
    return playlist_payload(
        _playlist_title(playlist),
        "listenbrainz",
        tracks,
        limit,
        cover_art=_playlist_cover_art(playlist),
        track_count=len(_playlist_tracks(playlist)),
    )


def fetch_listenbrainz_tracks(username: str, import_type: str, limit: int) -> Dict:
    if import_type == "recent":
        url = f"{BASE}/user/{username}/listens"
        params = {"count": limit}
        root_key = "listens"
    elif import_type == "loved":
        url = f"{BASE}/feedback/user/{username}/get-feedback"
        params = {"score": 1, "count": limit}
        root_key = "feedback"
    elif import_type == "playlists":
        playlists = fetch_listenbrainz_playlists(username, limit)
        if not playlists:
            return playlist_payload(f"ListenBrainz playlists for {username}", "listenbrainz", [], limit)
        return fetch_listenbrainz_playlist(playlists[0]["id"], limit)
    elif import_type.startswith("playlist:"):
        return fetch_listenbrainz_playlist(import_type.split(":", 1)[1], limit)
    else:
        raise ValueError("Invalid ListenBrainz import type")
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    payload = _payload(data)
    tracks = []
    for item in payload.get(root_key) or []:
        tracks.append(_recording_to_track(item, "listenbrainz"))
    return playlist_payload(f"ListenBrainz {import_type} for {username}", "listenbrainz", tracks, limit)
