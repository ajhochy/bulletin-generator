#!/usr/bin/env python3
"""
Local server for Worship Booklet Generator.
- Serves static files from the same directory
- Proxies PCO API requests
- Proxies and caches Google Calendar iCal feeds
- Provides REST API backed by JSON files in data/
"""

import http.server
import urllib.request
import urllib.error
import urllib.parse
import json
import base64
import re
import os
import sys
import platform
import threading
import subprocess
import tempfile
import zipfile
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Directory setup ────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    # Running as a PyInstaller bundle — static files are in _MEIPASS (read-only)
    BASE_DIR = Path(sys._MEIPASS)
    # Writable user data lives in the platform app-data directory
    if platform.system() == 'Darwin':
        DATA_DIR = Path.home() / 'Library' / 'Application Support' / 'BulletinGenerator'
    elif platform.system() == 'Windows':
        DATA_DIR = Path(os.environ.get('APPDATA', str(Path.home()))) / 'BulletinGenerator'
    else:
        DATA_DIR = Path.home() / '.bulletin-generator'
else:
    BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)

PROJECTS_FILE      = DATA_DIR / "projects.json"
ANNOUNCEMENTS_FILE = DATA_DIR / "announcements.json"
SETTINGS_FILE      = DATA_DIR / "settings.json"
SONGS_FILE         = DATA_DIR / "song_database.json"
MIGRATIONS_FILE    = DATA_DIR / "migrations.json"
# Example/seed files always live alongside the app code (read-only in frozen builds)
_EXAMPLE_DIR = BASE_DIR / "data"
PROJECTS_EXAMPLE_FILE      = _EXAMPLE_DIR / "projects.example.json"
ANNOUNCEMENTS_EXAMPLE_FILE = _EXAMPLE_DIR / "announcements.example.json"
SETTINGS_EXAMPLE_FILE      = _EXAMPLE_DIR / "settings.example.json"

# ── App version and update config ──────────────────────────────────────────────
APP_VERSION   = "1.08"
GITHUB_REPO   = "ajhochy/bulletin-generator"
# Watchtower HTTP API — default matches the service name in docker-compose.yml
WATCHTOWER_URL = os.environ.get("WATCHTOWER_URL", "http://watchtower:8080/v1/update")

PCO_BASE    = 'https://api.planningcenteronline.com/services/v2'
GOOGLE_CAL_API  = 'https://www.googleapis.com/calendar/v3'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
DEFAULT_EXCLUDE = ['sunday morning worship', 'sunday service', 'worship service']

# Deployment mode: 'server' (shared/hosted) or 'desktop' (local packaged install).
# Desktop mode disables multi-user collaboration features.
# Server mode disables desktop-only packaging/update features.
APP_MODE = os.environ.get("APP_MODE", "server").strip().lower()
if APP_MODE not in ("server", "desktop"):
    print(f"  [config] Unknown APP_MODE '{APP_MODE}', defaulting to 'server'")
    APP_MODE = "server"


def _load_dotenv(path):
    if not path.exists():
        return
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or key in os.environ:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ[key] = value
    except Exception as e:
        print(f"  [config] Failed to load {path.name}: {e}")


_load_dotenv(BASE_DIR / ".env")


def _parse_list_env(name):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except Exception:
        pass
    parts = re.split(r"[\n,]", raw)
    return [part.strip() for part in parts if part.strip()]


def _pco_auth_header():
    # Desktop mode: use stored OAuth access token if available
    settings = _read_json(SETTINGS_FILE, {})
    access_token = settings.get('pcoAccessToken', '').strip()
    if access_token:
        return f'Bearer {access_token}'
    # Server mode fallback: Basic auth from environment
    app_id = os.environ.get("PCO_APP_ID", "").strip()
    secret = os.environ.get("PCO_SECRET", "").strip()
    if not app_id or not secret:
        return None
    token = base64.b64encode(f"{app_id}:{secret}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _refresh_pco_token():
    """Exchange refresh_token for a new access_token. Returns new Bearer header or None."""
    settings = _read_json(SETTINGS_FILE, {})
    refresh_token = settings.get('pcoRefreshToken', '').strip()
    client_id     = os.environ.get('PCO_CLIENT_ID',     '').strip()
    client_secret = os.environ.get('PCO_CLIENT_SECRET', '').strip()
    if not refresh_token or not client_id or not client_secret:
        return None
    try:
        token_data = urllib.parse.urlencode({
            'grant_type':    'refresh_token',
            'refresh_token': refresh_token,
            'client_id':     client_id,
            'client_secret': client_secret,
        }).encode()
        req = urllib.request.Request(
            'https://api.planningcenteronline.com/oauth/token',
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            token_resp = json.loads(resp.read())
        new_access  = token_resp.get('access_token', '').strip()
        new_refresh = token_resp.get('refresh_token', '').strip()
        if not new_access:
            return None
        with _lock:
            s = _read_json(SETTINGS_FILE, {})
            s['pcoAccessToken']  = new_access
            if new_refresh:
                s['pcoRefreshToken'] = new_refresh
            _write_json(SETTINGS_FILE, s)
        print('  [oauth] PCO access token refreshed.')
        return f'Bearer {new_access}'
    except Exception as e:
        print(f'  [oauth] PCO token refresh failed: {e}')
        return None


def _google_auth_header():
    settings = _read_json(SETTINGS_FILE, {})
    token = settings.get('googleAccessToken', '').strip()
    return f'Bearer {token}' if token else None


def _refresh_google_token():
    """Exchange stored refresh_token for a new Google access_token."""
    settings = _read_json(SETTINGS_FILE, {})
    refresh_token = settings.get('googleRefreshToken', '').strip()
    client_id     = os.environ.get('GOOGLE_CLIENT_ID',     '').strip()
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '').strip()
    if not refresh_token or not client_id or not client_secret:
        return None
    try:
        token_data = urllib.parse.urlencode({
            'grant_type':    'refresh_token',
            'refresh_token': refresh_token,
            'client_id':     client_id,
            'client_secret': client_secret,
        }).encode()
        req = urllib.request.Request(
            GOOGLE_TOKEN_URL, data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_data = json.loads(resp.read())
        new_token = resp_data.get('access_token', '').strip()
        if not new_token:
            return None
        with _lock:
            s = _read_json(SETTINGS_FILE, {})
            s['googleAccessToken'] = new_token
            _write_json(SETTINGS_FILE, s)
        print('  [google] Access token refreshed.')
        return f'Bearer {new_token}'
    except Exception as e:
        print(f'  [google] Token refresh failed: {e}')
        return None


def _public_config():
    return {
        "appMode": APP_MODE,
        "appVersion": APP_VERSION,
        "pcoConfigured": _pco_auth_header() is not None,
        "googleConfigured": _google_auth_header() is not None,
        "calendarDefaults": {
            "urls": _parse_list_env("CALENDAR_ICAL_URLS"),
            "exclude": _parse_list_env("CALENDAR_EXCLUDE_TITLES") or DEFAULT_EXCLUDE[:],
        },
    }


def _initialize_local_file(path, example_path, default_value):
    if path.exists():
        return
    try:
        if example_path.exists():
            path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  [data] Initialized {path.name} from {example_path.name}")
            return
    except Exception as e:
        print(f"  [data] Failed to copy {example_path.name} to {path.name}: {e}")

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_value, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"  [data] Initialized {path.name} with defaults")
    except Exception as e:
        print(f"  [data] Failed to initialize {path.name}: {e}")

# Auto-detect Chrome/Chromium binary — works on macOS (dev) and Linux/Docker (prod)
def _find_chrome():
    candidates = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return candidates[-1]  # fallback to macOS path; will surface a clear error

CHROME_PATH = _find_chrome()

_lock = threading.Lock()


# ─── JSON file helpers ─────────────────────────────────────────────────────────

def _read_json(path, default):
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _write_json(path, data):
    # Callers are responsible for holding _lock before calling this.
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


# ─── iCal parsing ─────────────────────────────────────────────────────────────

def unfold_ical(text):
    """RFC 5545 line unfolding: remove CRLF followed by whitespace."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return re.sub(r'\n[ \t]', '', text)


def unescape_ical(value):
    """Unescape iCal text values."""
    value = value.replace('\\n', '\n').replace('\\N', '\n')
    value = value.replace('\\,', ',').replace('\\;', ';')
    value = value.replace('\\\\', '\\')
    return value


def parse_ical_dt(value, params=''):
    """Parse a DTSTART/DTEND value. Returns a dict with ISO string and allDay flag."""
    is_all_day = 'VALUE=DATE' in params or (len(value) == 8 and value.isdigit())

    if is_all_day:
        try:
            dt = datetime.strptime(value, '%Y%m%d')
            return {'iso': dt.strftime('%Y-%m-%d'), 'allDay': True}
        except ValueError:
            return None

    # DateTime with Z (UTC)
    if value.endswith('Z'):
        try:
            dt = datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            local_dt = dt.astimezone()
            return {'iso': local_dt.strftime('%Y-%m-%dT%H:%M:%S'), 'allDay': False}
        except ValueError:
            return None

    # DateTime without Z (floating / TZID)
    m = re.match(r'^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$', value)
    if m:
        yr, mo, dy, hr, mn, sc = (int(x) for x in m.groups())
        dt = datetime(yr, mo, dy, hr, mn, sc)
        return {'iso': dt.strftime('%Y-%m-%dT%H:%M:%S'), 'allDay': False}

    return None


def parse_ical_events(text):
    """Parse iCal text and return a list of event dicts."""
    text = unfold_ical(text)
    events = []
    ev = None

    for line in text.split('\n'):
        stripped = line.strip()
        if stripped == 'BEGIN:VEVENT':
            ev = {}
            continue
        if stripped == 'END:VEVENT':
            if ev is not None:
                events.append(ev)
            ev = None
            continue
        if ev is None:
            continue

        colon = line.find(':')
        if colon < 0:
            continue

        key_full = line[:colon]
        value    = line[colon + 1:]

        semi = key_full.find(';')
        key_base = (key_full[:semi] if semi >= 0 else key_full).upper().strip()
        params   = key_full[semi + 1:] if semi >= 0 else ''

        ev[key_base] = {'value': unescape_ical(value), 'params': params}

    return events


def get_week_window():
    """Return (start, end) as date objects for the upcoming Sunday–Saturday window."""
    today = datetime.now().date()
    dow = today.weekday()  # Monday=0, Sunday=6
    days_until_sunday = (6 - dow) % 7  # 0 if today is Sunday
    start = today + timedelta(days=days_until_sunday)
    end   = start + timedelta(days=6)
    return start, end


def fetch_and_parse_calendars(urls, exclude_titles):
    """Fetch all iCal URLs, parse, filter, deduplicate. Returns sorted event list."""
    if not urls:
        return []
    start_date, end_date = get_week_window()
    exclude_lower = {t.strip().lower() for t in exclude_titles}
    all_events = []
    any_success = False

    for url in urls:
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'WorshipBulletinProxy/1.0',
                'Accept': 'text/calendar',
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
            any_success = True
        except Exception as e:
            print(f'  [cal] Failed to fetch {url[:60]}…: {e}')
            continue

        try:
            raw_events = parse_ical_events(raw)
        except Exception as e:
            print(f'  [cal] Parse error: {e}')
            continue

        for ev in raw_events:
            start_field = ev.get('DTSTART')
            if not start_field:
                continue

            parsed_start = parse_ical_dt(start_field['value'], start_field.get('params', ''))
            if not parsed_start:
                continue

            ev_date_str = parsed_start['iso'][:10]
            try:
                ev_date = datetime.strptime(ev_date_str, '%Y-%m-%d').date()
            except ValueError:
                continue

            if ev_date < start_date or ev_date > end_date:
                continue

            title = (ev.get('SUMMARY', {}).get('value') or '').strip()
            if not title or title.lower() in exclude_lower:
                continue

            end_field = ev.get('DTEND')
            parsed_end = parse_ical_dt(end_field['value'], end_field.get('params', '')) if end_field else None

            location    = (ev.get('LOCATION',    {}).get('value') or '').strip()
            description = (ev.get('DESCRIPTION', {}).get('value') or '').strip()
            desc_first = next((l.strip() for l in description.split('\n') if l.strip()), '')

            all_events.append({
                'title':       title,
                'start':       parsed_start,
                'end':         parsed_end,
                'location':    location,
                'description': desc_first,
            })

    if not any_success:
        return None  # signals total failure

    # Deduplicate: same title + same start ISO string
    seen = set()
    deduped = []
    for ev in all_events:
        key = ev['title'].lower() + '|' + ev['start']['iso']
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)

    deduped.sort(key=lambda e: e['start']['iso'])
    return deduped


def fetch_google_cal_events(auth_header, calendar_ids, exclude_titles):
    """Fetch this week's events from Google Calendar API for given calendar IDs."""
    start_date, end_date = get_week_window()
    time_min = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    time_max = datetime.combine(end_date,   datetime.max.time().replace(microsecond=0)).replace(tzinfo=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    exclude_lower = {t.strip().lower() for t in exclude_titles}
    all_events = []

    for cal_id in calendar_ids:
        encoded_id = urllib.parse.quote(cal_id, safe='')
        params = urllib.parse.urlencode({
            'timeMin': time_min,
            'timeMax': time_max,
            'singleEvents': 'true',
            'orderBy': 'startTime',
            'maxResults': '100',
        })
        url = f'{GOOGLE_CAL_API}/calendars/{encoded_id}/events?{params}'
        req = urllib.request.Request(url, headers={
            'Authorization': auth_header,
            'Accept': 'application/json',
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f'  [google-cal] Failed to fetch calendar {cal_id}: {e}')
            continue

        for item in data.get('items', []):
            title = (item.get('summary') or '').strip()
            if not title or title.lower() in exclude_lower:
                continue
            start_raw = item.get('start', {})
            end_raw   = item.get('end',   {})
            if start_raw.get('date'):
                all_day = True
                iso_start = start_raw['date'] + 'T00:00:00'
                iso_end   = end_raw.get('date', start_raw['date']) + 'T00:00:00' if end_raw else None
            else:
                all_day = False
                iso_start = start_raw.get('dateTime', '')
                iso_end   = end_raw.get('dateTime')  if end_raw else None
            if not iso_start:
                continue
            all_events.append({
                'title':       title,
                'start':       {'iso': iso_start, 'allDay': all_day},
                'end':         {'iso': iso_end,   'allDay': all_day} if iso_end else None,
                'location':    (item.get('location') or '').strip(),
                'description': (item.get('description') or '').split('\n')[0].strip(),
            })

    seen = set()
    deduped = []
    for ev in all_events:
        key = ev['title'].lower() + '|' + ev['start']['iso']
        if key not in seen:
            seen.add(key)
            deduped.append(ev)
    deduped.sort(key=lambda e: e['start']['iso'])
    return deduped


# ─── Migration framework ───────────────────────────────────────────────────────

def _migration_001_songdb_extraction():
    """Move songDb out of settings.json into song_database.json."""
    if SONGS_FILE.exists():
        return  # Already done (by previous ad-hoc code or a prior run of this migration)
    settings = _read_json(SETTINGS_FILE, {})
    if 'songDb' in settings:
        _write_json(SONGS_FILE, settings.pop('songDb'))
        _write_json(SETTINGS_FILE, settings)
    else:
        _write_json(SONGS_FILE, [])


# Registry: list of (id, callable). Order matters — append only, never reorder.
_MIGRATION_REGISTRY = [
    ("M001_songdb_extraction", _migration_001_songdb_extraction),
]


def run_migrations():
    """Run any pending migrations at startup. Safe to call every time — idempotent."""
    applied = _read_json(MIGRATIONS_FILE, [])
    if not isinstance(applied, list):
        applied = []
    applied_set = set(applied)
    changed = False
    for migration_id, fn in _MIGRATION_REGISTRY:
        if migration_id in applied_set:
            continue
        try:
            fn()
            applied.append(migration_id)
            applied_set.add(migration_id)
            changed = True
            print(f"  [migration] Applied {migration_id}")
        except Exception as e:
            print(f"  [migration] ERROR in {migration_id}: {e} — stopping migration run")
            break  # Stop on first failure to avoid cascading issues
    if changed:
        _write_json(MIGRATIONS_FILE, applied)


# ─── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    # ── Logging ────────────────────────────────────────────────────────────────

    def log_message(self, fmt, *args):
        # Only log 4xx/5xx errors
        code = args[1] if len(args) > 1 else ""
        try:
            if int(code) >= 400:
                super().log_message(fmt, *args)
        except (ValueError, TypeError):
            pass

    def log_error(self, fmt, *args):
        print(f'  [server] {fmt % args}')

    # ── CORS ───────────────────────────────────────────────────────────────────

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_HEAD(self):
        # Block direct access to data files — same rule as do_GET
        path = self.path.split("?")[0]
        if path.startswith("/data/"):
            self._send_json({"error": "Forbidden"}, 403)
            return
        super().do_HEAD()

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _serve_nocache_static(self):
        """Serve a static file with Cache-Control: no-store so JS/CSS changes
        are always picked up immediately without a hard browser refresh."""
        rel = self.path.split("?")[0].lstrip("/")
        file_path = BASE_DIR / rel
        try:
            data = file_path.read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            self.send_response(404)
            self.end_headers()
            return
        ext = file_path.suffix.lower()
        ctype = "text/javascript; charset=utf-8" if ext == ".js" else "text/css; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _read_body_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    # ── Routing ────────────────────────────────────────────────────────────────

    def do_GET(self):
        path = self.path.split("?")[0]

        # Block direct access to raw data files — always serve via /api/* endpoints
        if path.startswith("/data/"):
            self._send_json({"error": "Forbidden"}, 403)
            return

        if path == "/" or path == "/index.html" or path == "/worship-booklet.html":
            try:
                content = (BASE_DIR / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error loading app: {e}".encode())
            return

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if path == "/api/projects":
            projects = _read_json(PROJECTS_FILE, [])
            self._send_json({"projects": projects})
            return

        if path == "/api/announcements":
            anns = _read_json(ANNOUNCEMENTS_FILE, [])
            self._send_json(anns)
            return

        if path == "/api/settings":
            settings = _read_json(SETTINGS_FILE, {})
            self._send_json(settings)
            return

        if path == "/api/songs":
            songs = _read_json(SONGS_FILE, [])
            self._send_json(songs)
            return

        if path == "/api/bootstrap":
            settings = _read_json(SETTINGS_FILE, {})
            songs = _read_json(SONGS_FILE, [])
            self._send_json({
                "settings": settings,
                "songDb": songs,
                "config": _public_config(),
            })
            return

        if path == "/oauth/pco/start":
            self._handle_pco_oauth_start()
            return

        if path == "/oauth/pco/callback":
            self._handle_pco_oauth_callback()
            return

        if path == "/oauth/google/start":
            self._handle_google_oauth_start()
            return

        if path == "/oauth/google/callback":
            self._handle_google_oauth_callback()
            return

        if path == "/api/google-calendars":
            self._handle_google_calendars()
            return

        if self.path.startswith("/pco-proxy/"):
            self._proxy_pco()
            return

        if self.path.startswith("/cal"):
            self._handle_cal()
            return

        # Serve static files (CSS, JS, images) from BASE_DIR via SimpleHTTPRequestHandler.
        # JS and CSS files get no-store so browser always fetches fresh copies during
        # development — prevents stale cached code after a server update.
        if path.startswith("/src/"):
            if path.endswith(".js") or path.endswith(".css"):
                # Intercept to inject cache-busting headers before delegating
                self._serve_nocache_static()
            else:
                super().do_GET()
            return

        if path == "/api/admin/check-update":
            self._handle_check_update()
            return

        self._send_json({"error": f"Not found: {path}"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]

        if path == "/api/projects":
            try:
                project = self._read_body_json()
            except Exception:
                self._send_json({"error": "invalid JSON"}, 400)
                return
            if not isinstance(project, dict) or "id" not in project:
                self._send_json({"error": "project must be an object with an id"}, 400)
                return
            with _lock:
                projects = _read_json(PROJECTS_FILE, [])
                idx = next((i for i, p in enumerate(projects) if p.get("id") == project["id"]), -1)
                if idx >= 0:
                    stored = projects[idx]
                    stored_rev = stored.get("revision")
                    client_rev = project.pop("_clientRevision", None)
                    # Conflict detection: reject if client is editing an older revision
                    if (APP_MODE == "server"
                            and stored_rev is not None
                            and client_rev is not None
                            and int(client_rev) < int(stored_rev)):
                        self._send_json({
                            "error": "conflict",
                            "projectId": project["id"],
                            "serverRevision": stored_rev,
                            "serverUpdatedAt": stored.get("updatedAt"),
                            "serverUpdatedBy": stored.get("updatedBy"),
                        }, 409)
                        return
                    # Increment revision and stamp server-side metadata
                    new_rev = int(stored_rev or 0) + 1
                    project["revision"] = new_rev
                    project["createdAt"] = stored.get("createdAt") or project.get("createdAt")
                    project["createdBy"] = stored.get("createdBy") or project.get("createdBy")
                    projects[idx] = project
                else:
                    project.pop("_clientRevision", None)
                    project.setdefault("revision", 1)
                    projects.append(project)
                _write_json(PROJECTS_FILE, projects)
                saved = projects[idx] if idx >= 0 else projects[-1]
            self._send_json({"ok": True, "revision": saved.get("revision")})
            return

        if path == "/api/announcements":
            try:
                anns = self._read_body_json()
            except Exception:
                self._send_json({"error": "invalid JSON"}, 400)
                return
            if not isinstance(anns, list):
                self._send_json({"error": "body must be an array"}, 400)
                return
            with _lock:
                _write_json(ANNOUNCEMENTS_FILE, anns)
            self._send_json({"ok": True})
            return

        if path == "/api/settings":
            try:
                partial = self._read_body_json()
            except Exception:
                self._send_json({"error": "invalid JSON"}, 400)
                return
            if not isinstance(partial, dict):
                self._send_json({"error": "body must be an object"}, 400)
                return
            with _lock:
                settings = _read_json(SETTINGS_FILE, {})
                for key, value in partial.items():
                    if value is None:
                        settings.pop(key, None)
                    else:
                        settings[key] = value
                _write_json(SETTINGS_FILE, settings)
            self._send_json({"ok": True})
            return

        if path == "/api/songs":
            try:
                songs = self._read_body_json()
            except Exception:
                self._send_json({"error": "invalid JSON"}, 400)
                return
            if not isinstance(songs, list):
                self._send_json({"error": "body must be an array"}, 400)
                return
            with _lock:
                _write_json(SONGS_FILE, songs)
            self._send_json({"ok": True})
            return

        if path == "/api/pdf":
            self._handle_pdf()
            return

        if path == "/api/pco-disconnect":
            with _lock:
                settings = _read_json(SETTINGS_FILE, {})
                settings.pop('pcoAccessToken', None)
                settings.pop('pcoRefreshToken', None)
                _write_json(SETTINGS_FILE, settings)
            self._send_json({"ok": True})
            return

        if path == "/api/google-disconnect":
            with _lock:
                settings = _read_json(SETTINGS_FILE, {})
                settings.pop('googleAccessToken', None)
                settings.pop('googleRefreshToken', None)
                settings.pop('googleCalendarIds', None)
                _write_json(SETTINGS_FILE, settings)
            self._send_json({"ok": True})
            return

        if path == "/api/admin/apply-update":
            self._handle_apply_update()
            return

        self._send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        path = self.path.split("?")[0]

        if path.startswith("/api/projects/"):
            project_id = path[len("/api/projects/"):]
            if not project_id:
                self._send_json({"error": "missing project id"}, 400)
                return
            with _lock:
                projects = _read_json(PROJECTS_FILE, [])
                projects = [p for p in projects if p.get("id") != project_id]
                _write_json(PROJECTS_FILE, projects)
            self._send_json({"ok": True})
            return

        self._send_json({"error": "not found"}, 404)

    # ── PCO OAuth (desktop mode) ───────────────────────────────────────────────

    def _handle_pco_oauth_start(self):
        client_id = os.environ.get('PCO_CLIENT_ID', '').strip()
        if not client_id:
            self._send_json({'error': 'PCO OAuth credentials not configured in desktop build.'}, 503)
            return
        port = self.server.server_address[1]
        redirect_uri = f'http://localhost:{port}/oauth/pco/callback'
        params = urllib.parse.urlencode({
            'client_id':     client_id,
            'redirect_uri':  redirect_uri,
            'response_type': 'code',
            'scope':         'services',
        })
        self.send_response(302)
        self.send_header('Location', f'https://api.planningcenteronline.com/oauth/authorize?{params}')
        self.end_headers()

    def _handle_pco_oauth_callback(self):
        qs     = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        code   = params.get('code', [None])[0]
        if not code:
            self.send_response(302)
            self.send_header('Location', '/?pco_error=denied')
            self.end_headers()
            return

        client_id     = os.environ.get('PCO_CLIENT_ID',     '').strip()
        client_secret = os.environ.get('PCO_CLIENT_SECRET', '').strip()
        port          = self.server.server_address[1]
        redirect_uri  = f'http://localhost:{port}/oauth/pco/callback'

        try:
            token_data = urllib.parse.urlencode({
                'grant_type':    'authorization_code',
                'code':          code,
                'client_id':     client_id,
                'client_secret': client_secret,
                'redirect_uri':  redirect_uri,
            }).encode()
            req = urllib.request.Request(
                'https://api.planningcenteronline.com/oauth/token',
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                token_resp = json.loads(resp.read())

            access_token  = token_resp.get('access_token', '').strip()
            refresh_token = token_resp.get('refresh_token', '').strip()
            if not access_token:
                raise ValueError('No access token returned by PCO.')

            with _lock:
                settings = _read_json(SETTINGS_FILE, {})
                settings['pcoAccessToken']  = access_token
                settings['pcoRefreshToken'] = refresh_token
                _write_json(SETTINGS_FILE, settings)

            self.send_response(302)
            self.send_header('Location', '/?pco_connected=1')
            self.end_headers()

        except Exception as e:
            print(f'  [oauth] PCO token exchange failed: {e}')
            self.send_response(302)
            self.send_header('Location', '/?pco_error=token')
            self.end_headers()

    # ── Google Calendar OAuth ──────────────────────────────────────────────────

    def _handle_google_oauth_start(self):
        client_id = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
        if not client_id:
            self._send_json({'error': 'Google OAuth credentials not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.'}, 503)
            return
        port = self.server.server_address[1]
        app_url = os.environ.get('APP_URL', '').strip().rstrip('/')
        redirect_uri = f'{app_url}/oauth/google/callback' if app_url else f'http://localhost:{port}/oauth/google/callback'
        params = urllib.parse.urlencode({
            'client_id':     client_id,
            'redirect_uri':  redirect_uri,
            'response_type': 'code',
            'scope':         'https://www.googleapis.com/auth/calendar.readonly',
            'access_type':   'offline',
            'prompt':        'consent',
        })
        self.send_response(302)
        self.send_header('Location', f'https://accounts.google.com/o/oauth2/v2/auth?{params}')
        self.end_headers()

    def _handle_google_oauth_callback(self):
        qs     = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        code   = params.get('code', [None])[0]
        if params.get('error') or not code:
            self.send_response(302)
            self.send_header('Location', '/?google_error=denied')
            self.end_headers()
            return

        client_id     = os.environ.get('GOOGLE_CLIENT_ID',     '').strip()
        client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '').strip()
        port          = self.server.server_address[1]
        app_url       = os.environ.get('APP_URL', '').strip().rstrip('/')
        redirect_uri  = f'{app_url}/oauth/google/callback' if app_url else f'http://localhost:{port}/oauth/google/callback'

        try:
            token_data = urllib.parse.urlencode({
                'grant_type':    'authorization_code',
                'code':          code,
                'client_id':     client_id,
                'client_secret': client_secret,
                'redirect_uri':  redirect_uri,
            }).encode()
            req = urllib.request.Request(
                GOOGLE_TOKEN_URL, data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                token_resp = json.loads(resp.read())

            access_token  = token_resp.get('access_token',  '').strip()
            refresh_token = token_resp.get('refresh_token', '').strip()
            if not access_token:
                raise ValueError('No access token returned by Google.')

            with _lock:
                s = _read_json(SETTINGS_FILE, {})
                s['googleAccessToken']  = access_token
                if refresh_token:
                    s['googleRefreshToken'] = refresh_token
                _write_json(SETTINGS_FILE, s)

            self.send_response(302)
            self.send_header('Location', '/?google_connected=1')
            self.end_headers()

        except Exception as e:
            print(f'  [google] Token exchange failed: {e}')
            self.send_response(302)
            self.send_header('Location', '/?google_error=token')
            self.end_headers()

    def _handle_google_calendars(self):
        """Return the user's Google Calendar list."""
        auth = _google_auth_header()
        if not auth:
            self._send_json({'error': 'Not connected to Google Calendar.'}, 401)
            return

        def _do_fetch(a):
            url = 'https://www.googleapis.com/calendar/v3/users/me/calendarList?maxResults=50'
            req = urllib.request.Request(url, headers={'Authorization': a, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())

        try:
            data = _do_fetch(auth)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                new_auth = _refresh_google_token()
                if new_auth:
                    try:
                        data = _do_fetch(new_auth)
                    except Exception as e2:
                        self._send_json({'error': str(e2)}, 500)
                        return
                else:
                    self._send_json({'error': 'Google token expired. Please reconnect.'}, 401)
                    return
            else:
                self._send_json({'error': f'Google API error {e.code}'}, e.code)
                return
        except Exception as e:
            self._send_json({'error': str(e)}, 500)
            return

        calendars = [
            {
                'id':      c['id'],
                'summary': c.get('summary', c['id']),
                'primary': c.get('primary', False),
            }
            for c in data.get('items', [])
        ]
        self._send_json({'calendars': calendars})

    # ── PDF generation ─────────────────────────────────────────────────────────

    def _handle_pdf(self):
        try:
            body = self._read_body_json()
        except Exception:
            self._send_json({"error": "invalid JSON"}, 400)
            return
        if not isinstance(body, dict) or "html" not in body:
            self._send_json({"error": "body must include html"}, 400)
            return

        html_content = body["html"]
        raw_name     = body.get("filename") or "bulletin"
        filename     = re.sub(r'[^\w\s\-.]', '', raw_name).strip() or "bulletin"
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        page_w = float(body.get("pageWidth",  5.5))
        page_h = float(body.get("pageHeight", 8.5))

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                html_path = os.path.join(tmpdir, "input.html")
                pdf_path  = os.path.join(tmpdir, "output.pdf")

                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)

                cmd = [
                    CHROME_PATH,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",               # required when running as root in Docker
                    "--disable-dev-shm-usage",    # avoids /dev/shm size issues in containers
                    "--run-all-compositor-stages-before-draw",
                    f"--print-to-pdf={pdf_path}",
                    "--print-to-pdf-no-header",
                    f"--paper-width={page_w}",
                    f"--paper-height={page_h}",
                    "--no-margins",
                    "--disable-extensions",
                    "--disable-background-networking",
                    f"file://{html_path}",
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=45)

                if result.returncode != 0 or not os.path.exists(pdf_path):
                    stderr = result.stderr.decode("utf-8", errors="replace")[:600]
                    print(f"  [pdf] Chrome exited {result.returncode}: {stderr}")
                    self._send_json({"error": f"Chrome did not produce a PDF. {stderr}"}, 500)
                    return

                with open(pdf_path, "rb") as f:
                    pdf_data = f.read()

        except subprocess.TimeoutExpired:
            self._send_json({"error": "PDF generation timed out (>45 s)"}, 500)
            return
        except Exception as e:
            import traceback; traceback.print_exc()
            self._send_json({"error": str(e)}, 500)
            return

        safe_fn = filename.encode("ascii", "ignore").decode() or "bulletin.pdf"
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(pdf_data)))
        self.send_header("Content-Disposition", f'attachment; filename="{safe_fn}"')
        self._cors_headers()
        self.end_headers()
        self.wfile.write(pdf_data)
        print(f"  [pdf] Generated {safe_fn} ({len(pdf_data):,} bytes)")

    # ── PCO proxy ──────────────────────────────────────────────────────────────

    def _proxy_pco(self):
        pco_path = self.path[len('/pco-proxy'):]
        url  = PCO_BASE + pco_path
        auth = _pco_auth_header()
        if not auth:
            self._send_json({
                "errors": [{
                    "detail": "Planning Center credentials are not configured on the server."
                }]
            }, 503)
            return

        req = urllib.request.Request(url, headers={
            'Authorization': auth,
            'Accept': 'application/json',
            'User-Agent': 'WorshipBulletinProxy/1.0',
        })

        def _do_request(r):
            with urllib.request.urlopen(r) as resp:
                return resp.read()

        try:
            data = _do_request(req)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors_headers()
            self.end_headers()
            self.wfile.write(data)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                # Token may be expired — attempt a silent refresh and retry once
                new_auth = _refresh_pco_token()
                if new_auth:
                    req2 = urllib.request.Request(url, headers={
                        'Authorization': new_auth,
                        'Accept': 'application/json',
                        'User-Agent': 'WorshipBulletinProxy/1.0',
                    })
                    try:
                        data = _do_request(req2)
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self._cors_headers()
                        self.end_headers()
                        self.wfile.write(data)
                        return
                    except urllib.error.HTTPError as e2:
                        e = e2
                    except Exception as e2:
                        self.send_response(500)
                        self.send_header('Content-Type', 'application/json')
                        self._cors_headers()
                        self.end_headers()
                        self.wfile.write(f'{{"errors":[{{"detail":"{e2}"}}]}}'.encode())
                        return
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self._cors_headers()
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self._cors_headers()
            self.end_headers()
            self.wfile.write(f'{{"errors":[{{"detail":"{e}"}}]}}'.encode())

    # ── Update endpoints ────────────────────────────────────────────────────────

    def _handle_check_update(self):
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"BulletinGenerator/{APP_VERSION}",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            latest_tag  = data.get("tag_name", "").lstrip("v")
            release_url = data.get("html_url", "")
            has_update  = bool(latest_tag) and latest_tag != APP_VERSION
            self._send_json({
                "current": APP_VERSION,
                "latest":  latest_tag,
                "url":     release_url,
                "hasUpdate": has_update,
            })
        except Exception as e:
            self._send_json({"error": f"Could not reach GitHub: {e}"}, 502)

    def _handle_apply_update(self):
        if APP_MODE == "server":
            self._apply_update_server()
        else:
            self._apply_update_desktop()

    def _apply_update_server(self):
        """Trigger Watchtower to pull the latest image and restart the container."""
        settings = _read_json(SETTINGS_FILE, {})
        token = settings.get("watchtowerToken", "").strip()
        if not token:
            self._send_json({"error": "Watchtower token not configured. Add it in Settings → App Updates."}, 400)
            return
        try:
            req = urllib.request.Request(
                WATCHTOWER_URL,
                data=b"",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
            self._send_json({"ok": True, "mode": "server",
                             "message": "Update triggered. Server will restart shortly."})
        except urllib.error.HTTPError as e:
            self._send_json({"error": f"Watchtower returned {e.code}: {e.reason}"}, 502)
        except Exception as e:
            self._send_json({"error": f"Could not reach Watchtower: {e}"}, 502)

    def _apply_update_desktop(self):
        """Download the latest macOS .app zip from GitHub Releases, extract, replace bundle."""
        if not getattr(sys, 'frozen', False):
            self._send_json({"error": "Auto-update only works in the packaged .app build."}, 400)
            return
        try:
            # 1. Fetch latest release metadata
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"BulletinGenerator/{APP_VERSION}",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                release = json.loads(resp.read())

            # 2. Find the macOS zip asset
            zip_url = None
            for asset in release.get("assets", []):
                name = asset.get("name", "")
                if name.endswith(".zip") and "macos" in name.lower():
                    zip_url = asset.get("browser_download_url")
                    break
            if not zip_url:
                for asset in release.get("assets", []):
                    if asset.get("name", "").endswith(".zip"):
                        zip_url = asset.get("browser_download_url")
                        break
            if not zip_url:
                self._send_json({"error": "No macOS zip asset found in the latest release."}, 404)
                return

            # 3. Download zip to a temp file
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_f:
                tmp_zip = tmp_f.name
            with urllib.request.urlopen(zip_url, timeout=120) as resp:
                with open(tmp_zip, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)

            # 4. Locate current .app bundle
            # sys.executable inside PyInstaller: <bundle>.app/Contents/MacOS/<exe>
            current_app = Path(sys.executable).parents[2]
            if not str(current_app).endswith(".app"):
                self._send_json({"error": f"Could not locate .app bundle (found: {current_app})"}, 500)
                Path(tmp_zip).unlink(missing_ok=True)
                return

            app_parent = current_app.parent
            app_name   = current_app.name

            # 5. Extract zip and find the .app inside
            with tempfile.TemporaryDirectory(dir=str(app_parent)) as tmp_dir:
                with zipfile.ZipFile(tmp_zip, "r") as zf:
                    zf.extractall(tmp_dir)

                new_app = None
                for item in Path(tmp_dir).iterdir():
                    if item.suffix == ".app":
                        new_app = item
                        break
                if new_app is None:
                    for sub in Path(tmp_dir).rglob("*.app"):
                        new_app = sub
                        break

                if new_app is None:
                    self._send_json({"error": "No .app bundle found in the downloaded zip."}, 500)
                    return

                # 6. Atomic replace: backup old, copy new
                backup = app_parent / (app_name + ".bak")
                if backup.exists():
                    shutil.rmtree(str(backup))
                current_app.rename(backup)
                shutil.copytree(str(new_app), str(app_parent / app_name))

            Path(tmp_zip).unlink(missing_ok=True)
            self._send_json({"ok": True, "mode": "desktop",
                             "message": "Update downloaded. Quit and relaunch the app to use the new version."})
        except Exception as e:
            import traceback; traceback.print_exc()
            self._send_json({"error": str(e)}, 500)

    # ── Calendar endpoint ──────────────────────────────────────────────────────

    def _handle_cal(self):
        try:
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)

            defaults = _public_config()["calendarDefaults"]
            urls = defaults["urls"]
            if 'urls' in params:
                try:
                    custom = json.loads(params['urls'][0])
                    if isinstance(custom, list):
                        urls = custom
                except Exception:
                    pass

            exclude = defaults["exclude"]
            if 'exclude' in params:
                try:
                    custom_ex = json.loads(params['exclude'][0])
                    if isinstance(custom_ex, list):
                        exclude = custom_ex
                except Exception:
                    pass

            # Prefer Google Calendar API if the user is connected and has selected calendars
            google_cal_ids = _read_json(SETTINGS_FILE, {}).get('googleCalendarIds', [])
            google_auth = _google_auth_header()
            if google_auth and google_cal_ids:
                result = fetch_google_cal_events(google_auth, google_cal_ids, exclude)
                if result is None or (isinstance(result, list) and len(result) == 0 and google_cal_ids):
                    # On 401 try refreshing once
                    new_auth = _refresh_google_token()
                    if new_auth:
                        result = fetch_google_cal_events(new_auth, google_cal_ids, exclude)
            else:
                result = fetch_and_parse_calendars(urls, exclude)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'max-age=900')
            self._cors_headers()
            self.end_headers()

            if result is None:
                payload = {'ok': False, 'events': [], 'error': 'All calendar fetches failed.'}
            else:
                payload = {'ok': True, 'events': result}

            self.wfile.write(json.dumps(payload).encode())

        except Exception as e:
            import traceback
            print(f'  [cal] Unhandled error: {e}')
            traceback.print_exc()
            try:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self._cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'events': [], 'error': str(e)}).encode())
            except Exception:
                pass


# ─── Entry point ───────────────────────────────────────────────────────────────

def run_server(port=8080):
    """Start the HTTP server. Called directly by launcher.py in desktop mode."""
    _initialize_local_file(PROJECTS_FILE, PROJECTS_EXAMPLE_FILE, [])
    _initialize_local_file(ANNOUNCEMENTS_FILE, ANNOUNCEMENTS_EXAMPLE_FILE, [])
    _initialize_local_file(SETTINGS_FILE, SETTINGS_EXAMPLE_FILE, {})
    run_migrations()
    os.chdir(str(BASE_DIR))
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    httpd = http.server.ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print(f'  Worship Booklet Generator v{APP_VERSION} running at:')
    print(f'  http://localhost:{port}/')
    print(f'  Data directory: {DATA_DIR}')
    print(f'  PCO configured: {"yes" if _public_config()["pcoConfigured"] else "no"}')
    print(f'  App mode: {APP_MODE}')
    if APP_MODE == 'desktop':
        print(f'  PCO OAuth redirect: http://localhost:{port}/oauth/pco/callback')
    print(f'\n  Press Ctrl+C to stop.\n')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('Server stopped.')
        httpd.server_close()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port)
