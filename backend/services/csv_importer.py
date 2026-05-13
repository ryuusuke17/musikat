from __future__ import annotations

import csv
import io
from typing import Dict, List

from .playlist_importer import (
    ALBUM_KEYS,
    ARTIST_KEYS,
    DURATION_KEYS,
    TITLE_KEYS,
    URL_KEYS,
    ImportedTrack,
    compact_space,
    normalize_key,
    parse_duration_ms,
    split_artist_title,
)


def _field_map(fieldnames: List[str]) -> Dict[str, str]:
    mapped: Dict[str, str] = {}
    for name in fieldnames:
        norm = normalize_key(name)
        if norm in TITLE_KEYS and "title" not in mapped:
            mapped["title"] = name
        elif norm in ARTIST_KEYS and "artist" not in mapped:
            mapped["artist"] = name
        elif norm in ALBUM_KEYS and "album" not in mapped:
            mapped["album"] = name
        elif norm in DURATION_KEYS and "duration" not in mapped:
            mapped["duration"] = name
        elif norm in URL_KEYS and "url" not in mapped:
            mapped["url"] = name
    return mapped


def parse_csv_playlist(data: bytes | str) -> List[ImportedTrack]:
    text = data.decode("utf-8-sig", errors="replace") if isinstance(data, bytes) else data
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []
    fields = _field_map(reader.fieldnames)
    tracks: List[ImportedTrack] = []
    for row in reader:
        title = compact_space(row.get(fields.get("title", ""), ""))
        artist = compact_space(row.get(fields.get("artist", ""), ""))
        if not title:
            combined = compact_space(next((v for v in row.values() if v), ""))
            inferred_artist, inferred_title = split_artist_title(combined)
            title = inferred_title
            artist = artist or inferred_artist
        tracks.append(
            ImportedTrack(
                title=title,
                artist=artist,
                album=compact_space(row.get(fields.get("album", ""), "")),
                duration_ms=parse_duration_ms(row.get(fields.get("duration", ""), "")),
                url=compact_space(row.get(fields.get("url", ""), "")),
                source="csv",
                raw=dict(row),
            )
        )
    return tracks
