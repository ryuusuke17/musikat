from __future__ import annotations

import re
from typing import List, Optional

from .playlist_importer import ImportedTrack, compact_space, infer_track_from_path, parse_duration_ms, split_artist_title


EXTINF_RE = re.compile(r"^#EXTINF:(?P<duration>-?\d+)?(?:\s+[^,]*)?,(?P<label>.*)$", re.I)


def _track_from_extinf(label: str, duration: Optional[str], next_path: str = "") -> ImportedTrack:
    artist, title = split_artist_title(label)
    track = ImportedTrack(
        title=title,
        artist=artist,
        duration_ms=parse_duration_ms(duration or "0"),
        url=next_path,
        source="m3u",
    )
    if next_path and (not track.artist or not track.title):
        inferred = infer_track_from_path(next_path, source="m3u")
        track.artist = track.artist or inferred.artist
        track.title = track.title or inferred.title
        track.album = inferred.album
    return track


def parse_m3u_playlist(data: bytes | str) -> List[ImportedTrack]:
    text = data.decode("utf-8-sig", errors="replace") if isinstance(data, bytes) else data
    lines = [line.strip() for line in text.splitlines()]
    tracks: List[ImportedTrack] = []
    pending_extinf = None
    for line in lines:
        if not line:
            continue
        ext = EXTINF_RE.match(line)
        if ext:
            pending_extinf = ext.groupdict()
            continue
        if line.startswith("#"):
            continue
        if pending_extinf:
            label = compact_space(pending_extinf.get("label"))
            tracks.append(_track_from_extinf(label, pending_extinf.get("duration"), line))
            pending_extinf = None
            continue
        tracks.append(infer_track_from_path(line, source="m3u"))
    if pending_extinf:
        tracks.append(_track_from_extinf(compact_space(pending_extinf.get("label")), pending_extinf.get("duration")))
    return tracks
