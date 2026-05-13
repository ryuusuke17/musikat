from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass
class ImportedTrack:
    title: str
    artist: str = ""
    album: str = ""
    duration_ms: int = 0
    url: str = ""
    source: str = "unknown"
    isrc: str = ""
    cover_art: str = ""
    identifiers: Dict[str, str] = field(default_factory=dict)
    raw: Dict = field(default_factory=dict)

    def to_dict(self, index: int) -> Dict:
        return {
            "import_id": f"{self.source}-{index}",
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration_ms": self.duration_ms,
            "url": self.url,
            "source": self.source,
            "isrc": self.isrc,
            "cover_art": self.cover_art,
            "identifiers": self.identifiers,
            "raw": self.raw,
        }


def compact_space(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


TITLE_KEYS = {
    "title",
    "track",
    "tracktitle",
    "song",
    "songtitle",
    "name",
    "trackname",
}
ARTIST_KEYS = {
    "artist",
    "artists",
    "artistname",
    "trackartist",
    "creator",
    "performer",
    "author",
}
ALBUM_KEYS = {"album", "albumtitle", "albumname", "release"}
DURATION_KEYS = {"duration", "length", "durationms", "time"}
URL_KEYS = {"url", "link", "spotifyurl", "deezerurl", "uri"}


def parse_duration_ms(value: object) -> int:
    if value is None:
        return 0
    raw = compact_space(str(value))
    if not raw:
        return 0
    if raw.isdigit():
        n = int(raw)
        return n if n > 10_000 else n * 1000
    parts = raw.split(":")
    if all(p.isdigit() for p in parts):
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + int(part)
        return seconds * 1000
    return 0


def split_artist_title(value: str) -> Tuple[str, str]:
    text = compact_space(value)
    if not text:
        return "", ""
    text = re.sub(r"\.[a-z0-9]{2,5}$", "", text, flags=re.I)
    text = text.replace("_", " ")
    for sep in (" - ", " – ", " — ", " -- "):
        if sep in text:
            left, right = [compact_space(p) for p in text.split(sep, 1)]
            if left and right:
                return left, right
    return "", text


def infer_track_from_path(path: str, source: str = "m3u") -> ImportedTrack:
    clean = compact_space(path).replace("\\", "/")
    parts = [p for p in clean.split("/") if p]
    filename = parts[-1] if parts else clean
    artist, title = split_artist_title(filename)
    album = ""
    if not artist and len(parts) >= 3:
        artist = compact_space(parts[-3])
        album = compact_space(parts[-2])
        _, title = split_artist_title(filename)
    elif len(parts) >= 2:
        album = compact_space(parts[-2])
    return ImportedTrack(title=title, artist=artist, album=album, url=path, source=source)


def dedupe_tracks(tracks: Iterable[ImportedTrack]) -> List[ImportedTrack]:
    seen = set()
    out: List[ImportedTrack] = []
    for track in tracks:
        title = compact_space(track.title)
        artist = compact_space(track.artist)
        if not title:
            continue
        key = (title.lower(), artist.lower(), compact_space(track.album).lower())
        if key in seen:
            continue
        seen.add(key)
        track.title = title
        track.artist = artist
        track.album = compact_space(track.album)
        out.append(track)
    return out


def search_query(track: Dict) -> str:
    title = compact_space(track.get("title") or track.get("name"))
    artist = compact_space(track.get("artist"))
    album = compact_space(track.get("album"))
    return " ".join(p for p in (artist, title, album) if p)


def _score_text(a: str, b: str) -> float:
    a = compact_space(a).lower()
    b = compact_space(b).lower()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def match_confidence(imported: Dict, candidate: Dict) -> float:
    title_score = _score_text(imported.get("title", ""), candidate.get("name", ""))
    artist_score = _score_text(imported.get("artist", ""), candidate.get("artist", ""))
    swapped_title_score = _score_text(imported.get("artist", ""), candidate.get("name", ""))
    swapped_artist_score = _score_text(imported.get("title", ""), candidate.get("artist", ""))
    album_score = _score_text(imported.get("album", ""), candidate.get("album", ""))
    duration_score = 0.0
    imported_ms = int(imported.get("duration_ms") or 0)
    candidate_ms = int(candidate.get("duration_ms") or 0)
    if imported_ms and candidate_ms:
        diff = abs(imported_ms - candidate_ms)
        duration_score = max(0.0, 1.0 - (diff / max(imported_ms, candidate_ms, 1)))
    direct = (title_score * 0.55) + (artist_score * 0.3) + (album_score * 0.1) + (duration_score * 0.05)
    swapped = (swapped_title_score * 0.55) + (swapped_artist_score * 0.3) + (album_score * 0.1) + (duration_score * 0.05)
    score = max(direct, swapped)
    if not imported.get("artist"):
        score = (title_score * 0.8) + (album_score * 0.15) + (duration_score * 0.05)
    return round(min(score, 1.0), 3)


def match_tracks(tracks: List[Dict], metadata_service, limit: int = 5) -> List[Dict]:
    matched: List[Dict] = []
    for track in tracks:
        item = dict(track)
        query = search_query(item)
        item["match_query"] = query
        item["match_status"] = "unmatched"
        item["confidence"] = 0.0
        item["matched_track"] = None
        item["candidates"] = []
        if not query:
            matched.append(item)
            continue
        try:
            candidates = metadata_service.search_tracks(query, limit=limit)
        except Exception as exc:
            item["match_status"] = "error"
            item["match_error"] = str(exc)
            matched.append(item)
            continue
        scored = []
        for candidate in candidates:
            c = dict(candidate)
            c["confidence"] = match_confidence(item, c)
            scored.append(c)
        scored.sort(key=lambda c: c.get("confidence", 0), reverse=True)
        item["candidates"] = scored
        if scored:
            best = scored[0]
            item["matched_track"] = best
            item["confidence"] = best["confidence"]
            item["match_status"] = "matched" if best["confidence"] >= 0.78 else "low_confidence"
        matched.append(item)
    return matched


def _optional_int(value: object) -> Optional[int]:
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def playlist_payload(
    name: str,
    source: str,
    tracks: List[ImportedTrack],
    limit: int,
    cover_art: str = "",
    track_count: Optional[int] = None,
    duration_ms: Optional[int] = None,
) -> Dict:
    limited = dedupe_tracks(tracks)[: max(1, limit)]
    total_duration = duration_ms if duration_ms is not None else sum(int(track.duration_ms or 0) for track in limited)
    fallback_art = next((track.cover_art for track in limited if track.cover_art), "")
    return {
        "playlist": {
            "name": name or "Imported playlist",
            "source": source,
            "track_count": _optional_int(track_count) or len(limited),
            "imported_track_count": len(limited),
            "duration_ms": int(total_duration or 0),
            "cover_art": cover_art or fallback_art,
        },
        "tracks": [track.to_dict(i) for i, track in enumerate(limited)],
    }
