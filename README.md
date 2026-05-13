# Musikat — Navidrome and local downloads

Search **Deezer** (default, no API key) or **Spotify** (optional credentials) for tracks and albums, download audio from **YouTube** with **yt-dlp**, apply ID3 tags and artwork, then save to your **browser downloads** or copy into **one or more Navidrome music library folders** on the server.

Choose the catalog in the web UI (**Catalog**) or set `DEFAULT_METADATA_PROVIDER` in `.env`.

## Screenshots

### Main Interface
![Main Interface](images/main-interface.png)

### Download Queue with Progress Bars
![Download Queue](images/download-queue.png)

## Features

- Search **Deezer** or **Spotify** for tracks and albums
- Import playlists from **CSV**, **M3U/M3U8**, **Spotify**, **Deezer**, **Last.fm**, and **ListenBrainz** with preview, matching, and selected-track queueing
- Download from YouTube using catalog metadata; optional **YouTube cookies** when YouTube blocks automation
- ID3 tagging (artist, album, cover art) via the metadata service
- **Download to:** local (browser) **or** any **configured Navidrome music root** (multiple libraries supported — no need to run separate app instances)
- Web UI with download queue and status polling
- Background **library sync** (optional): scan Navidrome folders and align “already downloaded” state with the catalog

## Architecture

| Layer | Technology |
|--------|------------|
| Frontend | HTML, CSS, vanilla JavaScript |
| Backend | Python **FastAPI** |
| Catalog | **Deezer** (public search) or **Spotify Web API** (optional) |
| Audio | **yt-dlp** + **FFmpeg** |
| Tags | **mutagen** |
| Server library | Files copied under **Navidrome** music path(s); optional Navidrome API for scans |

## Prerequisites

**Docker:** Docker and Docker Compose  

**Manual:** Python 3.8+ (3.11+ recommended), **FFmpeg** on `PATH`, optional Navidrome instance  

**Spotify** in the UI requires `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in `backend/.env`.

## Installation

### Docker Compose (recommended)

```bash
git clone https://github.com/soggy8/musikat.git
cd musikat

cp backend/env.example backend/.env
# Edit backend/.env: Navidrome path(s), optional Spotify, DEFAULT_METADATA_PROVIDER

docker-compose up -d
```

Open [http://localhost:8000](http://localhost:8000).  

Mount your Navidrome music directory in `docker-compose.yml` (see [DOCKER.md](DOCKER.md)).

### Manual install

See [SETUP.md](SETUP.md).

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Install **FFmpeg** (e.g. `sudo apt install ffmpeg` on Debian/Ubuntu, `brew install ffmpeg` on macOS).

## Configuration (`backend/.env`)

Copy `backend/env.example` to `backend/.env` and adjust.

### Metadata catalog

| Variable | Description |
|----------|-------------|
| `DEFAULT_METADATA_PROVIDER` | `deezer` (default) or `spotify` |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | Required if you use Spotify in the UI |
| `SPOTIFY_REDIRECT_URI` | OAuth redirect (default `http://localhost:8000/callback`) |

### Playlist import

| Variable | Description |
|----------|-------------|
| `DEFAULT_PLAYLIST_MATCH_PROVIDER` | `deezer` or `spotify`; used when matching imported playlist rows |
| `PLAYLIST_IMPORT_LIMIT` | Maximum tracks parsed/imported from a playlist preview (default `250`) |
| `LASTFM_API_KEY` | Required for Last.fm loved/top/recent track imports |

Spotify playlist imports use the same `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` credentials as Spotify catalog search. Deezer and ListenBrainz imports use public APIs.

### Navidrome — one or multiple library folders

The app writes files **on disk** under paths the server is allowed to use. Navidrome should use the same folder(s) as its music library.

| Variable | Description |
|----------|-------------|
| `NAVIDROME_MUSIC_PATH` | Single absolute path (default in code: `/music` if unset). Used when `NAVIDROME_MUSIC_PATHS` is not set. |
| `NAVIDROME_MUSIC_PATHS` | Optional. Comma- or newline-separated **absolute** paths. Each appears as a separate **Download to** target. |
| `NAVIDROME_MUSIC_LABELS` | Optional. Same order as `NAVIDROME_MUSIC_PATHS`; labels shown in the UI (defaults to folder basename). |
| `NAVIDROME_API_URL` | Navidrome base URL (for scans), e.g. `http://localhost:4533` |
| `NAVIDROME_USERNAME` / `NAVIDROME_PASSWORD` | Optional; for triggering library scans via API |
| `NAVIDROME_SYNC_ENABLED` | `true`/`false` — background scan of library paths to sync “already downloaded” hints (default on) |
| `NAVIDROME_SYNC_INTERVAL_HOURS` | Between sync runs |
| `NAVIDROME_SYNC_INITIAL_DELAY_SEC` | Delay before first sync after startup |

**Examples**

Single folder (typical Docker mount):

```env
NAVIDROME_MUSIC_PATH=/music
```

Multiple libraries:

```env
NAVIDROME_MUSIC_PATHS=/data/music/rock,/data/music/classical
NAVIDROME_MUSIC_LABELS=Rock,Classical
```

### Downloads and API

| Variable | Description |
|----------|-------------|
| `DOWNLOAD_DIR` | Server temp/staging for downloads (default `./downloads`) |
| `OUTPUT_FORMAT` / `AUDIO_QUALITY` | Default encode settings |
| `YOUTUBE_COOKIES_PATH` | Netscape cookies file for yt-dlp when YouTube blocks requests |
| `FFMPEG_LOCATION` | Optional ffmpeg executable or bin directory; if unset, Musikat uses bundled `imageio-ffmpeg` when available |
| `API_HOST` / `API_PORT` | Bind address |
| `CORS_ORIGINS` | Comma-separated allowed origins |

## Running

```bash
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Or `python app.py` if your entrypoint wraps uvicorn. The UI is served from the same process (no separate frontend server).

## Usage

1. Open the app in the browser.
2. Under **Download to**, choose **My Downloads Folder (System)** or a **Navidrome** path (loaded from `GET /api/navidrome/libraries` / your env).
3. Pick **Catalog** (Deezer or Spotify).
4. Search tracks or albums, then download. Watch the queue for progress.
5. To import a playlist, use **Import Playlist**, preview the source tracks, click **Match tracks**, select the rows you want, then queue or download them.
6. **Local:** the browser saves the finished file. **Navidrome:** the server copies the file under the selected music root (Artist/Album layout).

## How it works

1. **Search** — Deezer or Spotify returns track/album metadata and IDs.
2. **Match** — YouTube candidates are chosen (with optional confirmation if confidence is low).
3. **Download** — yt-dlp fetches audio; FFmpeg converts if needed.
4. **Tag** — Metadata service writes tags and artwork.
5. **Deliver** — Either serve to the browser or copy into the chosen Navidrome root; optional Navidrome API notification for scanning.

## API (selected)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/health` | Status, `navidrome_path`, `navidrome_libraries`, etc. |
| GET | `/api/metadata/providers` | Deezer / Spotify and whether Spotify is configured |
| GET | `/api/navidrome/libraries` | `{ "libraries": [ { "path", "label" }, ... ] }` — roots from env |
| GET | `/api/formats` | Audio format and quality defaults |
| POST | `/api/search` | Body: `query`, `provider`, `limit` |
| POST | `/api/search/albums` | Album search |
| POST | `/api/download` | Body includes `track_id`, `location` (`local` \| `navidrome`), optional `navidrome_library` (absolute path; must match server config), `provider`, format/quality |
| POST | `/api/download/album` | Album download; same `location` / `navidrome_library` pattern |
| POST | `/api/reverse/download` | YouTube → metadata flow |
| POST | `/api/playlists/import/csv` | CSV upload preview |
| POST | `/api/playlists/import/m3u` | M3U/M3U8 upload preview |
| POST | `/api/playlists/import/spotify` | Spotify playlist URL import |
| POST | `/api/playlists/import/deezer` | Deezer playlist URL import |
| POST | `/api/playlists/import/lastfm` | Last.fm loved/top/recent import |
| POST | `/api/playlists/import/listenbrainz` | ListenBrainz loved/recent/playlists import |
| POST | `/api/playlists/match` | Match imported rows with the selected catalog |
| POST | `/api/playlists/queue` | Queue selected matched playlist tracks for download |
| GET | `/api/track/{id}/exists` | Duplicate check; supports `location` and optional `navidrome_library` |
| GET | `/api/download/status/{track_id}` | Job status |

Full behavior is defined in `backend/app.py`.

## Project structure

```
musikat/
├── backend/
│   ├── app.py
│   ├── config.py
│   ├── requirements.txt
│   ├── env.example
│   ├── static/              # app.js, styles.css
│   ├── templates/           # index.html
│   ├── services/            # deezer, spotify, youtube, metadata, navidrome
│   ├── utils/               # file_handler, job_store, navidrome_library_sync
│   └── tests/
├── images/
├── Dockerfile
├── docker-compose.yml
├── DOCKER.md
├── DEPLOYMENT.md
├── SETUP.md
└── README.md
```

## Troubleshooting

### No search results

- Try the other catalog or a more specific query (artist + title).

### YouTube errors (“Sign in to confirm you’re not a bot”, 403, etc.)

- Install FFmpeg and ensure it is on `PATH`.
- Export **cookies** (Netscape format) and set `YOUTUBE_COOKIES_PATH` (see [yt-dlp FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)). Cookies expire; re-export if downloads start failing.

### Navidrome: file not appearing or upload fails

- Paths must be **writable** by the process running Musikat.
- For multiple roots, each path in `NAVIDROME_MUSIC_PATHS` must match what you select in the UI (server validates against the allowlist).
- Check `GET /api/navidrome/libraries` matches your Docker mounts and permissions.

### CORS

- Add your site origin to `CORS_ORIGINS` in `.env` (required if the browser loads the UI from a **different origin** than the API, e.g. another port or domain).

### Reverse proxy (HTTPS, subpath)

If Musikat is served under a path such as `https://example.com/musikat/`, nginx must forward requests to the app and ideally send `X-Forwarded-Prefix: /musikat` so links and env match. The frontend also **infers** `/musikat` from the browser URL when that header is missing, so API calls target `/musikat/api/...` instead of `/api/...` (which would 404).

## Legal

Use for **personal** use only. Respect copyright and the terms of Deezer, Spotify, YouTube, and your jurisdiction.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Pull requests are welcome.

## More docs

- [DOCKER.md](DOCKER.md) — Docker deployment
- [DEPLOYMENT.md](DEPLOYMENT.md) — production notes
- [SETUP.md](SETUP.md) — manual setup
