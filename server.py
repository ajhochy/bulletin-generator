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
import copy
import cgi
import mimetypes

# PyInstaller bundles Python without the system CA certificates.
# Use certifi's bundled CA bundle so all HTTPS requests verify correctly.
try:
    import ssl
    import certifi
    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
except Exception:
    pass
import subprocess
import tempfile
import zipfile
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from propresenter_export import export_items_to_zip
    _PP_EXPORT_AVAILABLE = True
except ImportError:
    _PP_EXPORT_AVAILABLE = False

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
TEMPLATES_FILE     = DATA_DIR / "templates.json"
FONTS_DIR          = DATA_DIR / "fonts"
USER_FONTS_DIR     = FONTS_DIR / "user"
FONT_CACHE_DIR     = FONTS_DIR / "cache"
# Example/seed files always live alongside the app code (read-only in frozen builds)
_EXAMPLE_DIR = BASE_DIR / "data"
PROJECTS_EXAMPLE_FILE      = _EXAMPLE_DIR / "projects.example.json"
ANNOUNCEMENTS_EXAMPLE_FILE = _EXAMPLE_DIR / "announcements.example.json"
SETTINGS_EXAMPLE_FILE      = _EXAMPLE_DIR / "settings.example.json"
TEMPLATES_EXAMPLE_FILE     = _EXAMPLE_DIR / "templates.example.json"

ALLOWED_FONT_EXTS = {".ttf", ".otf", ".woff", ".woff2"}
SYSTEM_FONT_FAMILIES = {"system-ui", "arial", "helvetica", "georgia", "times new roman", "trebuchet ms", "verdana"}


def _slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug or "font"


def _font_family_from_slug(slug):
    return " ".join(part.capitalize() for part in _slugify(slug).split("-"))


def _font_format(ext):
    return {
        ".ttf": "truetype",
        ".otf": "opentype",
        ".woff": "woff",
        ".woff2": "woff2",
    }.get(ext.lower(), "truetype")


def _safe_child(base, *parts):
    root = Path(base).resolve()
    candidate = root.joinpath(*parts).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("invalid path")
    return candidate


def _classic_template(page_size="5.5x8.5"):
    return {
        "id": "classic",
        "name": "Classic",
        "builtIn": True,
        "pageSize": page_size or "5.5x8.5",
        "cssVars": {},
        "typeFormats": {},
        "zones": [
            {"id": "z-cover",   "binding": "cover",            "order": 1, "enabled": True,  "match": {}, "elements": {"churchName": {}, "serviceDate": {}, "subtitle": {}}},
            {"id": "z-ann",     "binding": "announcements",    "order": 2, "enabled": True,  "match": {}, "elements": {"title": {}, "body": {}, "url": {}}},
            {"id": "z-oow-section", "binding": "pco_items",    "order": 3, "enabled": True,  "match": {"type": "section"}, "elements": {"heading": {}}},
            {"id": "z-oow-song",    "binding": "pco_items",    "order": 4, "enabled": True,  "match": {"type": "song"}, "elements": {"songTitle": {}, "stanzaText": {}, "copyright": {}}},
            {"id": "z-oow-liturgy", "binding": "pco_items",    "order": 5, "enabled": True,  "match": {"type": "liturgy"}, "elements": {"title": {}, "bodyParagraph": {}}},
            {"id": "z-oow-label",   "binding": "pco_items",    "order": 6, "enabled": True,  "match": {"type": "label"}, "elements": {"title": {}, "body": {}}},
            {"id": "z-cal",     "binding": "calendar",         "order": 7, "enabled": True,  "match": {}, "elements": {"dayHeading": {}, "eventTitle": {}, "eventTime": {}, "eventDescription": {}}},
            {"id": "z-serving", "binding": "serving_schedule", "order": 8, "enabled": True,  "match": {}, "elements": {"weekHeading": {}, "teamName": {}, "serviceTime": {}, "positionLabel": {}, "volunteerName": {}}},
            {"id": "z-staff",   "binding": "staff",            "order": 9, "enabled": True,  "match": {}, "elements": {"staffName": {}, "staffRole": {}, "staffEmail": {}}},
        ],
    }


def _modern_template():
    return {
        "id": "modern",
        "name": "Modern",
        "builtIn": True,
        "pageSize": "5.5x8.5",
        "cssVars": {
            "fontFamily": "Open Sans",
            "primary": "#1f2933",
            "muted": "#64748b",
            "accent": "#2f5d62",
            "border": "#cbd5d1",
        },
        "typeFormats": {},
        "zones": [
            {"id": "modern-cover", "binding": "cover", "order": 1, "enabled": True, "match": {}, "elements": {
                "churchName": {"fontFamily": "Open Sans", "size": "lg", "bold": True, "color": "#1f2933", "align": "center"},
                "serviceDate": {"fontFamily": "Open Sans", "size": "sm", "color": "#64748b", "align": "center"},
                "subtitle": {"fontFamily": "Times New Roman", "size": "xl", "italic": True, "color": "#2f5d62", "align": "center"}
            }},
            {"id": "modern-ann", "binding": "announcements", "order": 2, "enabled": True, "match": {}, "elements": {
                "title": {"fontFamily": "Open Sans", "bold": True, "color": "#2f5d62"},
                "body": {"fontFamily": "Open Sans", "size": "sm", "color": "#1f2933"},
                "url": {"fontFamily": "Open Sans", "size": "sm", "color": "#64748b"}
            }},
            {"id": "modern-section", "binding": "pco_items", "order": 3, "enabled": True, "match": {"type": "section"}, "elements": {
                "heading": {"fontFamily": "Open Sans", "bold": True, "size": "lg", "color": "#2f5d62", "align": "center"}
            }},
            {"id": "modern-song", "binding": "pco_items", "order": 4, "enabled": True, "match": {"type": "song"}, "elements": {
                "songTitle": {"fontFamily": "Times New Roman", "italic": True, "size": "lg", "color": "#1f2933"},
                "stanzaText": {"fontFamily": "Times New Roman", "size": "sm", "color": "#1f2933"},
                "copyright": {"fontFamily": "Open Sans", "size": "sm", "color": "#64748b", "layout": {"position": "inline", "row": "title-row", "align": "right", "verticalAlign": "baseline", "gap": "0.45rem"}}
            }},
            {"id": "modern-liturgy", "binding": "pco_items", "order": 5, "enabled": True, "match": {"type": "liturgy"}, "elements": {
                "title": {"fontFamily": "Open Sans", "bold": True, "color": "#2f5d62"},
                "bodyParagraph": {"fontFamily": "Times New Roman", "size": "sm", "color": "#1f2933"}
            }},
            {"id": "modern-label", "binding": "pco_items", "order": 6, "enabled": True, "match": {"type": "label"}, "elements": {
                "title": {"fontFamily": "Open Sans", "bold": True, "color": "#1f2933"},
                "body": {"fontFamily": "Times New Roman", "size": "sm", "color": "#1f2933"}
            }},
            {"id": "modern-cal", "binding": "calendar", "order": 7, "enabled": True, "match": {}, "elements": {
                "dayHeading": {"fontFamily": "Open Sans", "bold": True, "color": "#2f5d62"},
                "eventTitle": {"fontFamily": "Open Sans", "bold": True, "color": "#1f2933"},
                "eventTime": {"fontFamily": "Open Sans", "size": "sm", "color": "#64748b"},
                "eventDescription": {"fontFamily": "Open Sans", "size": "sm", "color": "#64748b"}
            }},
            {"id": "modern-serving", "binding": "serving_schedule", "order": 8, "enabled": True, "match": {}, "elements": {
                "weekHeading": {"fontFamily": "Open Sans", "bold": True, "color": "#2f5d62"},
                "teamName": {"fontFamily": "Open Sans", "italic": True, "color": "#64748b"},
                "serviceTime": {"fontFamily": "Open Sans", "size": "sm", "color": "#64748b"},
                "positionLabel": {"fontFamily": "Open Sans", "bold": True, "color": "#1f2933"},
                "volunteerName": {"fontFamily": "Open Sans", "color": "#1f2933"}
            }},
            {"id": "modern-staff", "binding": "staff", "order": 9, "enabled": True, "match": {}, "elements": {
                "staffName": {"fontFamily": "Open Sans", "bold": True, "color": "#1f2933"},
                "staffRole": {"fontFamily": "Open Sans", "italic": True, "color": "#64748b"},
                "staffEmail": {"fontFamily": "Open Sans", "size": "sm", "color": "#2f5d62"}
            }},
        ],
    }


def _builtin_templates():
    return [_classic_template(), _modern_template()]


def _backfill_project_doc_templates():
    projects = _read_json(PROJECTS_FILE, [])
    if not isinstance(projects, list):
        return False

    changed = False
    for project in projects:
        if not isinstance(project, dict):
            continue
        state = project.get("state")
        if not isinstance(state, dict):
            continue
        existing = state.get("activeDocTemplate")
        if isinstance(existing, dict) and isinstance(existing.get("zones"), list) and existing["zones"]:
            continue
        page_size = "5.5x8.5"
        if isinstance(existing, dict):
            page_size = existing.get("pageSize") or page_size
        migrated = _classic_template(page_size)
        if isinstance(existing, dict):
            migrated.update(copy.deepcopy(existing))
            migrated["zones"] = copy.deepcopy(_classic_template(page_size)["zones"])
        state["activeDocTemplate"] = migrated
        changed = True

    if changed:
        _write_json(PROJECTS_FILE, projects)
    return changed

# ── App version and update config ──────────────────────────────────────────────
APP_VERSION    = os.environ.get("APP_VERSION", "1.12.1").lstrip("v")
GITHUB_REPO    = "ajhochy/bulletin-generator"
# Watchtower HTTP API — internal Docker network only, never exposed externally.
# Token is a shared default between the app and the Watchtower sidecar in
# docker-compose.yml. Advanced deployments can override via WATCHTOWER_URL /
# WATCHTOWER_TOKEN env vars.
WATCHTOWER_URL   = os.environ.get("WATCHTOWER_URL",   "http://watchtower:8080/v1/update")
WATCHTOWER_TOKEN = os.environ.get("WATCHTOWER_TOKEN", "bulletin-updater")

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


def _is_placeholder_oauth_value(value):
    v = (value or '').strip()
    if not v:
        return True
    placeholder_markers = (
        'your_app_',
        'your-google-',
        'your-pco-',
        'replace-me',
        'example',
        'placeholder',
    )
    lower_v = v.lower()
    return any(marker in lower_v for marker in placeholder_markers)


def _oauth_config_error_redirect(provider, detail):
    msg = urllib.parse.quote(detail[:200])
    return f'/?{provider}_error=config&detail={msg}&tab=page-settings'


def _pco_auth_header():
    """Return the OAuth Bearer header from stored access token, or None."""
    settings = _read_json(SETTINGS_FILE, {})
    access_token = settings.get('pcoAccessToken', '').strip()
    if access_token:
        return f'Bearer {access_token}'
    return None


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
        "driveConfigured": bool(
            _read_json(SETTINGS_FILE, {}).get('googleDriveScopeGranted')
        ),
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

# Auto-detect Chrome/Chromium binary — works on macOS, Linux, and Windows.
# Override with CHROME_PATH env var for custom installs.
def _find_chrome():
    env_override = os.environ.get('CHROME_PATH', '').strip()
    if env_override:
        return env_override

    import platform
    system = platform.system()

    if system == 'Windows':
        candidates = [
            os.path.join(os.environ.get('PROGRAMFILES', r'C:\Program Files'),
                         r'Google\Chrome\Application\chrome.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'),
                         r'Google\Chrome\Application\chrome.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''),
                         r'Google\Chrome\Application\chrome.exe'),
        ]
    elif system == 'Darwin':
        candidates = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
        ]
    else:  # Linux / Docker
        candidates = [
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
        ]

    for c in candidates:
        if c and os.path.isfile(c):
            return c

    raise RuntimeError(
        'Chrome not found. Install Google Chrome or set the CHROME_PATH '
        'environment variable to your Chrome/Chromium binary path.'
    )

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
    end   = start + timedelta(days=8)
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
    """Fetch this week's events from Google Calendar API for given calendar IDs.
    Returns None if any calendar returns 401/403 (signals auth failure to caller).
    Returns [] if auth succeeds but there are no events in the window.
    Returns a list of events otherwise.
    """
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
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                # Auth failure — signal caller to refresh token, not just an empty calendar
                print(f'  [google-cal] Auth error ({e.code}) for calendar {cal_id} — token may be expired')
                return None
            print(f'  [google-cal] HTTP {e.code} fetching calendar {cal_id}: {e}')
            continue
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


def _migration_002_classic_template_default():
    """Ensure templates/projects have a backward-compatible Classic template.

    Projects saved before the template system was introduced will have no
    activeDocTemplate.zones. The Classic template (all-empty elements) is a
    perfect no-op: it preserves the hardcoded CSS defaults exactly, so existing
    bulletins look identical after the migration.
    """
    templates = _read_json(TEMPLATES_FILE, [])
    if not isinstance(templates, list):
        templates = []
    if not any(t.get("id") == "classic" for t in templates if isinstance(t, dict)):
        templates.insert(0, _classic_template())
        _write_json(TEMPLATES_FILE, templates)

    _backfill_project_doc_templates()


def _migration_003_project_template_backfill():
    """Backfill project templates for installs that already ran M002."""
    _backfill_project_doc_templates()


def _migration_004_classic_staff_zone_enabled():
    """Keep Classic visually aligned with the pre-template staff toggle behavior."""
    templates = _read_json(TEMPLATES_FILE, [])
    if not isinstance(templates, list):
        return
    changed = False
    for template in templates:
        if not isinstance(template, dict) or template.get("id") != "classic":
            continue
        for zone in template.get("zones") or []:
            if isinstance(zone, dict) and zone.get("binding") == "staff" and zone.get("enabled") is False:
                zone["enabled"] = True
                changed = True
    if changed:
        _write_json(TEMPLATES_FILE, templates)


def _sync_builtin_templates():
    templates = _read_json(TEMPLATES_FILE, [])
    if not isinstance(templates, list):
        templates = []
    by_id = {t.get("id"): i for i, t in enumerate(templates) if isinstance(t, dict)}
    changed = False
    for builtin in _builtin_templates():
        idx = by_id.get(builtin["id"])
        if idx is None:
            templates.append(builtin)
            changed = True
        else:
            existing = templates[idx]
            if existing.get("builtIn") or builtin["id"] in {"classic", "modern"}:
                keep_page_size = existing.get("pageSize") or builtin.get("pageSize")
                merged = copy.deepcopy(builtin)
                merged["pageSize"] = keep_page_size
                if existing != merged:
                    templates[idx] = merged
                    changed = True
    if changed:
        _write_json(TEMPLATES_FILE, templates)
    return changed


def _migration_005_builtin_template_presets():
    """Refresh built-in templates and seed Modern for existing installs."""
    _sync_builtin_templates()


# Registry: list of (id, callable). Order matters — append only, never reorder.
_MIGRATION_REGISTRY = [
    ("M001_songdb_extraction",        _migration_001_songdb_extraction),
    ("M002_classic_template_default", _migration_002_classic_template_default),
    ("M003_project_template_backfill", _migration_003_project_template_backfill),
    ("M004_classic_staff_zone_enabled", _migration_004_classic_staff_zone_enabled),
    ("M005_builtin_template_presets", _migration_005_builtin_template_presets),
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
        if self.path.split("?")[0].startswith("/data/"):
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

    def _send_bytes(self, data, content_type, status=200, cache_control="public, max-age=31536000"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    # ── Routing ────────────────────────────────────────────────────────────────

    # ── Routing tables ─────────────────────────────────────────────────────────
    # Each entry: (path_pattern, handler_method_name)
    # Patterns ending in '/' use startswith matching; others require exact equality.

    _GET_ROUTES = [
        ('/data/',                    '_handle_forbidden'),
        ('/',                         '_handle_index'),
        ('/index.html',               '_handle_index'),
        ('/worship-booklet.html',     '_handle_index'),
        ('/favicon.ico',              '_handle_favicon'),
        ('/api/projects',             '_handle_get_projects'),
        ('/api/announcements',        '_handle_get_announcements'),
        ('/api/settings',             '_handle_get_settings'),
        ('/api/songs',                '_handle_get_songs'),
        ('/api/templates',            '_handle_get_templates'),
        ('/api/fonts',                '_handle_get_fonts'),
        ('/api/bootstrap',            '_handle_bootstrap'),
        ('/api/google-calendars',     '_handle_google_calendars'),
        ('/api/admin/check-update',   '_handle_check_update'),
        ('/api/admin/update-status',  '_handle_update_status'),
        ('/oauth/pco/start',          '_handle_pco_oauth_start'),
        ('/oauth/pco/callback',       '_handle_pco_oauth_callback'),
        ('/oauth/google/start',       '_handle_google_oauth_start'),
        ('/oauth/google/callback',    '_handle_google_oauth_callback'),
        ('/pco-proxy/',               '_proxy_pco'),
        ('/fonts/cache/',             '_handle_google_font_cache'),
        ('/fonts/user/',              '_handle_user_font_file'),
        ('/cal',                      '_handle_cal'),
        ('/src/',                     '_handle_static'),
    ]

    _POST_ROUTES = [
        ('/api/projects',             '_handle_post_projects'),
        ('/api/announcements',        '_handle_post_announcements'),
        ('/api/settings',             '_handle_post_settings'),
        ('/api/songs',                '_handle_post_songs'),
        ('/api/templates',            '_handle_post_templates'),
        ('/api/fonts',                '_handle_post_fonts'),
        ('/api/pdf',                  '_handle_pdf'),
        ('/api/propresenter-export',  '_handle_propresenter_export'),
        ('/api/drive/upload',         '_handle_drive_upload'),
        ('/api/pco-disconnect',       '_handle_pco_disconnect'),
        ('/api/google-disconnect',    '_handle_google_disconnect'),
        ('/api/admin/apply-update',   '_handle_apply_update'),
    ]

    _DELETE_ROUTES = [
        ('/api/projects/',            '_handle_delete_project'),
        ('/api/templates/',           '_handle_delete_template'),
        ('/api/fonts/',               '_handle_delete_font'),
    ]

    def _route(self, routes):
        """Dispatch to the first matching handler. Returns True if matched."""
        path = self.path.split("?")[0]
        for pattern, handler in routes:
            if pattern == '/':
                matched = path == '/'
            elif pattern.endswith('/'):
                matched = path.startswith(pattern)
            else:
                matched = path == pattern
            if matched:
                getattr(self, handler)()
                return True
        return False

    def do_GET(self):
        if not self._route(self._GET_ROUTES):
            self._send_json({"error": f"Not found: {self.path.split('?')[0]}"}, 404)

    def do_POST(self):
        if not self._route(self._POST_ROUTES):
            self._send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        if not self._route(self._DELETE_ROUTES):
            self._send_json({"error": "not found"}, 404)

    # ── Route handlers (GET) ───────────────────────────────────────────────────

    def _handle_forbidden(self):
        self._send_json({"error": "Forbidden"}, 403)

    def _handle_index(self):
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

    def _handle_favicon(self):
        self.send_response(204)
        self.end_headers()

    def _handle_get_projects(self):
        self._send_json({"projects": _read_json(PROJECTS_FILE, [])})

    def _handle_get_announcements(self):
        self._send_json(_read_json(ANNOUNCEMENTS_FILE, []))

    def _handle_get_settings(self):
        self._send_json(_read_json(SETTINGS_FILE, {}))

    def _handle_get_songs(self):
        self._send_json(_read_json(SONGS_FILE, []))

    def _handle_bootstrap(self):
        self._send_json({
            "settings": _read_json(SETTINGS_FILE, {}),
            "songDb":   _read_json(SONGS_FILE, []),
            "config":   _public_config(),
        })

    def _handle_static(self):
        """Serve static files; inject no-cache headers for JS/CSS."""
        path = self.path.split("?")[0]
        if path.endswith(".js") or path.endswith(".css"):
            self._serve_nocache_static()
        else:
            super().do_GET()

    # ── Route handlers (POST) ──────────────────────────────────────────────────

    def _handle_post_projects(self):
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
                # Conflict detection: reject if client is editing an older revision.
                # Also reject when client_rev is None (client didn't know the revision) and
                # the server already has a versioned copy — prevents silent overwrites of
                # versioned projects by clients loading old pre-revision data.
                if (APP_MODE == "server"
                        and stored_rev is not None
                        and int(stored_rev) > 0
                        and (client_rev is None or int(client_rev) < int(stored_rev))):
                    self._send_json({
                        "error": "conflict",
                        "projectId": project["id"],
                        "serverRevision": stored_rev,
                        "serverUpdatedAt": stored.get("updatedAt"),
                        "serverUpdatedBy": stored.get("updatedBy"),
                    }, 409)
                    return
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

    def _handle_post_announcements(self):
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

    def _handle_post_settings(self):
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

    def _handle_post_songs(self):
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

    def _handle_pco_disconnect(self):
        with _lock:
            settings = _read_json(SETTINGS_FILE, {})
            settings.pop('pcoAccessToken', None)
            settings.pop('pcoRefreshToken', None)
            _write_json(SETTINGS_FILE, settings)
        self._send_json({"ok": True})

    def _handle_google_disconnect(self):
        with _lock:
            settings = _read_json(SETTINGS_FILE, {})
            settings.pop('googleAccessToken', None)
            settings.pop('googleRefreshToken', None)
            settings.pop('googleCalendarIds', None)
            settings.pop('googleDriveScopeGranted', None)
            settings.pop('googleDriveFolderId', None)
            _write_json(SETTINGS_FILE, settings)
        self._send_json({"ok": True})

    # ── Route handlers (DELETE) ────────────────────────────────────────────────

    def _handle_delete_project(self):
        path = self.path.split("?")[0]
        project_id = path[len("/api/projects/"):]
        if not project_id:
            self._send_json({"error": "missing project id"}, 400)
            return
        with _lock:
            projects = _read_json(PROJECTS_FILE, [])
            projects = [p for p in projects if p.get("id") != project_id]
            _write_json(PROJECTS_FILE, projects)
        self._send_json({"ok": True})

    # ── Templates ─────────────────────────────────────────────────────────────

    def _handle_get_templates(self):
        self._send_json(_read_json(TEMPLATES_FILE, []))

    def _validate_template(self, template):
        if not isinstance(template, dict):
            return "template must be an object"
        if not isinstance(template.get("id"), str) or not template["id"].strip():
            return "template must include an id"
        if not isinstance(template.get("name"), str) or not template["name"].strip():
            return "template must include a name"
        if "zones" not in template or not isinstance(template["zones"], list):
            return "template must include zones"
        if template.get("builtIn"):
            return "built-in templates cannot be modified"
        for zone in template["zones"]:
            if not isinstance(zone, dict):
                return "zone must be an object"
            if not isinstance(zone.get("id"), str) or not zone.get("id"):
                return "zone must include an id"
            if zone.get("binding") not in {"cover", "announcements", "pco_items", "calendar", "serving_schedule", "staff"}:
                return "zone has invalid binding"
            if not isinstance(zone.get("elements", {}), dict):
                return "zone elements must be an object"
        return None

    def _handle_post_templates(self):
        try:
            template = self._read_body_json()
        except Exception:
            self._send_json({"error": "invalid JSON"}, 400)
            return
        error = self._validate_template(template)
        if error:
            status = 403 if "built-in" in error else 400
            self._send_json({"error": error}, status)
            return
        template["id"] = _slugify(template["id"])
        template["builtIn"] = False
        with _lock:
            templates = _read_json(TEMPLATES_FILE, [])
            idx = next((i for i, t in enumerate(templates) if t.get("id") == template["id"]), -1)
            if idx >= 0:
                # Preserve builtIn flag if the stored record has it (prevent downgrade attack)
                if templates[idx].get("builtIn"):
                    self._send_json({"error": "built-in templates cannot be modified"}, 403)
                    return
                templates[idx] = template
            else:
                templates.append(template)
            _write_json(TEMPLATES_FILE, templates)
        self._send_json({"ok": True})

    def _handle_delete_template(self):
        path = self.path.split("?")[0]
        template_id = path[len("/api/templates/"):]
        if not template_id:
            self._send_json({"error": "missing template id"}, 400)
            return
        with _lock:
            templates = _read_json(TEMPLATES_FILE, [])
            target = next((t for t in templates if t.get("id") == template_id), None)
            if target and target.get("builtIn"):
                self._send_json({"error": "built-in templates cannot be deleted"}, 403)
                return
            templates = [t for t in templates if t.get("id") != template_id]
            _write_json(TEMPLATES_FILE, templates)
        self._send_json({"ok": True})

    # ── Fonts ────────────────────────────────────────────────────────────────

    def _list_user_fonts(self):
        fonts = []
        if USER_FONTS_DIR.exists():
            for family_dir in sorted(p for p in USER_FONTS_DIR.iterdir() if p.is_dir()):
                files = sorted(f.name for f in family_dir.iterdir() if f.is_file() and f.suffix.lower() in ALLOWED_FONT_EXTS)
                if not files:
                    continue
                fonts.append({
                    "family": _font_family_from_slug(family_dir.name),
                    "slug": family_dir.name,
                    "source": "user",
                    "files": files,
                    "cssUrl": f"/fonts/user/{family_dir.name}/font.css",
                })
        return fonts

    def _list_cached_fonts(self):
        fonts = []
        if FONT_CACHE_DIR.exists():
            for family_dir in sorted(p for p in FONT_CACHE_DIR.iterdir() if p.is_dir()):
                if not (family_dir / "font.css").exists():
                    continue
                fonts.append({
                    "family": _font_family_from_slug(family_dir.name),
                    "slug": family_dir.name,
                    "source": "google",
                    "cssUrl": f"/fonts/cache/{family_dir.name}/font.css",
                })
        return fonts

    def _handle_get_fonts(self):
        self._send_json({"user": self._list_user_fonts(), "cached": self._list_cached_fonts()})

    def _handle_post_fonts(self):
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            self._send_json({"error": "multipart/form-data required"}, 400)
            return
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": ctype,
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            },
        )
        if "file" not in form:
            self._send_json({"error": "missing file"}, 400)
            return
        field = form["file"]
        if isinstance(field, list):
            field = field[0]
        filename = Path(field.filename or "").name
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_FONT_EXTS:
            self._send_json({"error": "font must be TTF, OTF, WOFF, or WOFF2"}, 400)
            return
        family = ""
        if "family" in form:
            family = str(form["family"].value or "").strip()
        if not family:
            family = Path(filename).stem
        slug = _slugify(family)
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-") or f"{slug}{ext}"
        dest_dir = _safe_child(USER_FONTS_DIR, slug)
        dest_dir.mkdir(parents=True, exist_ok=True)
        data = field.file.read()
        if not data:
            self._send_json({"error": "empty font file"}, 400)
            return
        _safe_child(dest_dir, safe_name).write_bytes(data)
        self._send_json({"ok": True, "font": {
            "family": family,
            "slug": slug,
            "source": "user",
            "files": [safe_name],
            "cssUrl": f"/fonts/user/{slug}/font.css",
        }})

    def _handle_delete_font(self):
        path = self.path.split("?")[0]
        slug = _slugify(urllib.parse.unquote(path[len("/api/fonts/"):]))
        if not slug:
            self._send_json({"error": "missing font family"}, 400)
            return
        target = _safe_child(USER_FONTS_DIR, slug)
        if target.exists():
            shutil.rmtree(target)
        self._send_json({"ok": True})

    def _handle_user_font_file(self):
        path = urllib.parse.unquote(self.path.split("?")[0])
        rest = path[len("/fonts/user/"):].strip("/")
        parts = rest.split("/", 1)
        if len(parts) != 2:
            self._send_json({"error": "font file not found"}, 404)
            return
        slug = _slugify(parts[0])
        file_name = Path(parts[1]).name
        font_dir = _safe_child(USER_FONTS_DIR, slug)
        if file_name == "font.css":
            css = self._build_user_font_css(slug, font_dir).encode("utf-8")
            self._send_bytes(css, "text/css; charset=utf-8", cache_control="no-store")
            return
        file_path = _safe_child(font_dir, file_name)
        if not file_path.exists() or file_path.suffix.lower() not in ALLOWED_FONT_EXTS:
            self._send_json({"error": "font file not found"}, 404)
            return
        self._send_bytes(file_path.read_bytes(), mimetypes.guess_type(file_path.name)[0] or "font/woff2")

    def _build_user_font_css(self, slug, font_dir):
        family = _font_family_from_slug(slug)
        if not font_dir.exists():
            return ""
        rules = []
        for file_path in sorted(font_dir.iterdir()):
            if file_path.suffix.lower() not in ALLOWED_FONT_EXTS:
                continue
            rules.append(
                "@font-face { "
                f"font-family: \"{family}\"; "
                f"src: url(\"/fonts/user/{slug}/{file_path.name}\") format(\"{_font_format(file_path.suffix)}\"); "
                "font-weight: 400 900; font-style: normal; font-display: swap; }"
            )
        return "\n".join(rules)

    def _handle_google_font_cache(self):
        path = urllib.parse.unquote(self.path.split("?")[0])
        rest = path[len("/fonts/cache/"):].strip("/")
        parts = rest.split("/", 1)
        if len(parts) != 2:
            self._send_json({"error": "font file not found"}, 404)
            return
        slug = _slugify(parts[0])
        file_name = Path(parts[1]).name
        cache_dir = _safe_child(FONT_CACHE_DIR, slug)
        if file_name == "font.css":
            css_path = cache_dir / "font.css"
            if not css_path.exists():
                self._cache_google_font(slug, cache_dir)
            if css_path.exists():
                self._send_bytes(css_path.read_bytes(), "text/css; charset=utf-8", cache_control="public, max-age=3600")
            else:
                self._send_bytes(b"", "text/css; charset=utf-8", cache_control="no-store")
            return
        file_path = _safe_child(cache_dir, file_name)
        if not file_path.exists():
            self._send_json({"error": "font file not found"}, 404)
            return
        self._send_bytes(file_path.read_bytes(), mimetypes.guess_type(file_path.name)[0] or "font/woff2")

    def _cache_google_font(self, slug, cache_dir):
        family = _font_family_from_slug(slug)
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            query = urllib.parse.urlencode({"family": f"{family}:wght@400;600;700", "display": "swap"})
            req = urllib.request.Request(
                f"https://fonts.googleapis.com/css2?{query}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                css = resp.read().decode("utf-8")
            urls = re.findall(r"url\\((https://[^)]+)\\)", css)
            for idx, url in enumerate(urls):
                ext = Path(urllib.parse.urlparse(url).path).suffix or ".woff2"
                local_name = f"{slug}-{idx}{ext}"
                with urllib.request.urlopen(url, timeout=20) as font_resp:
                    _safe_child(cache_dir, local_name).write_bytes(font_resp.read())
                css = css.replace(url, f"/fonts/cache/{slug}/{local_name}")
            (cache_dir / "font.css").write_text(css, encoding="utf-8")
        except Exception as e:
            print(f"  [fonts] Google font cache failed for {family}: {e}")
            (cache_dir / "font.css").write_text("", encoding="utf-8")

    # ── PCO OAuth ──────────────────────────────────────────────────────────────

    def _handle_pco_oauth_start(self):
        client_id = os.environ.get('PCO_CLIENT_ID', '').strip()
        if not client_id:
            self._send_json({'error': 'PCO OAuth credentials not configured.'}, 503)
            return
        app_url = os.environ.get('APP_URL', '').strip().rstrip('/')
        if app_url:
            redirect_uri = f'{app_url}/oauth/pco/callback'
        else:
            port = self.server.server_address[1]
            redirect_uri = f'http://localhost:{port}/oauth/pco/callback'
        params = urllib.parse.urlencode({
            'client_id':     client_id,
            'redirect_uri':  redirect_uri,
            'response_type': 'code',
            'scope':         'services',
            'prompt':        'login',
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
        app_url = os.environ.get('APP_URL', '').strip().rstrip('/')
        if app_url:
            redirect_uri = f'{app_url}/oauth/pco/callback'
        else:
            port = self.server.server_address[1]
            redirect_uri = f'http://localhost:{port}/oauth/pco/callback'

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
            detail = urllib.parse.quote(str(e)[:200])
            self.send_response(302)
            self.send_header('Location', f'/?pco_error=token&detail={detail}')
            self.end_headers()

    # ── Google Calendar OAuth ──────────────────────────────────────────────────

    def _handle_google_oauth_start(self):
        client_id = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
        client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '').strip()
        if _is_placeholder_oauth_value(client_id) or _is_placeholder_oauth_value(client_secret):
            detail = (
                'Google OAuth is not configured for this build. '
                'Set a real GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET '
                'in desktop_config.py for desktop builds or .env for server mode.'
            )
            self.send_response(302)
            self.send_header('Location', _oauth_config_error_redirect('google', detail))
            self.end_headers()
            return
        port = self.server.server_address[1]
        app_url = os.environ.get('APP_URL', '').strip().rstrip('/')
        redirect_uri = f'{app_url}/oauth/google/callback' if app_url else f'http://localhost:{port}/oauth/google/callback'
        params = urllib.parse.urlencode({
            'client_id':     client_id,
            'redirect_uri':  redirect_uri,
            'response_type': 'code',
            'scope':         'https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/drive.file',
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
                s['googleAccessToken']       = access_token
                s['googleDriveScopeGranted'] = True
                if refresh_token:
                    s['googleRefreshToken'] = refresh_token
                _write_json(SETTINGS_FILE, s)

            self.send_response(302)
            self.send_header('Location', '/?google_connected=1&tab=page-settings')
            self.end_headers()

        except Exception as e:
            print(f'  [google] Token exchange failed: {e}')
            detail = urllib.parse.quote(str(e)[:200])
            self.send_response(302)
            self.send_header('Location', f'/?google_error=token&detail={detail}&tab=page-settings')
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
        MAX_PDF_HTML_BYTES = 5 * 1024 * 1024  # 5 MB
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > MAX_PDF_HTML_BYTES:
            self._send_json({'error': 'Request body too large (limit 5 MB)'}, 413)
            return

        try:
            body = self._read_body_json()
        except Exception:
            self._send_json({"error": "invalid JSON"}, 400)
            return
        if not isinstance(body, dict) or "html" not in body:
            self._send_json({"error": "body must include html"}, 400)
            return

        html_content = body["html"]
        if not isinstance(html_content, str) or not html_content.strip():
            self._send_json({"error": "html must be a non-empty string"}, 400)
            return
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

    _PCO_HEADERS = {
        'Accept': 'application/json',
        'User-Agent': 'WorshipBulletinProxy/1.0',
    }

    def _pco_build_request(self, auth):
        """Build a urllib Request for the PCO API using this handler's path."""
        url = PCO_BASE + self.path[len('/pco-proxy'):]
        return urllib.request.Request(url, headers={**self._PCO_HEADERS, 'Authorization': auth})

    def _pco_do_request(self, req):
        """Execute a PCO request and return raw response bytes."""
        with urllib.request.urlopen(req) as resp:
            return resp.read()

    def _pco_send_raw(self, data):
        """Write raw PCO API bytes directly to the response (passthrough)."""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _pco_passthrough_error(self, e):
        """Forward a PCO HTTPError status + body to the client unchanged."""
        self.send_response(e.code)
        self.send_header('Content-Type', 'application/json')
        self._cors_headers()
        self.end_headers()
        self.wfile.write(e.read())

    def _proxy_pco(self):
        auth = _pco_auth_header()
        if not auth:
            return self._send_json({"errors": [{"detail": "Planning Center credentials are not configured."}]}, 503)
        try:
            self._pco_send_raw(self._pco_do_request(self._pco_build_request(auth)))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                new_auth = _refresh_pco_token()
                if new_auth:
                    try:
                        self._pco_send_raw(self._pco_do_request(self._pco_build_request(new_auth)))
                        return
                    except urllib.error.HTTPError as e2:
                        e = e2
                    except Exception as e2:
                        self._send_json({"errors": [{"detail": str(e2)}]}, 500); return
            self._pco_passthrough_error(e)
        except Exception as e:
            self._send_json({"errors": [{"detail": str(e)}]}, 500)

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

    def _handle_update_status(self):
        """Return update environment info for diagnostics."""
        import shutil
        docker_available = shutil.which("docker") is not None
        socket_exists    = os.path.exists("/var/run/docker.sock")
        self._send_json({
            "watchtowerUrl":      WATCHTOWER_URL,
            "watchtowerToken":    bool(WATCHTOWER_TOKEN),
            "dockerCliAvailable": docker_available,
            "dockerSocketExists": socket_exists,
            "mode":               APP_MODE,
        })

    def _handle_apply_update(self):
        if APP_MODE == "server":
            self._apply_update_server()
        else:
            self._apply_update_desktop()

    def _handle_propresenter_export(self):
        """Export bulletin items as ProPresenter .pro files in a ZIP."""
        if not _PP_EXPORT_AVAILABLE:
            self._send_json({"error": "ProPresenter export module not available."}, 500)
            return
        try:
            body = self._read_body_json()
        except Exception:
            self._send_json({"error": "invalid JSON"}, 400)
            return

        if not isinstance(body, dict):
            self._send_json({"error": "body must be an object"}, 400)
            return

        try:
            items = body.get("items", [])
            project_name = body.get("projectName", "bulletin")
            song_db = body.get("songDb")

            if not isinstance(items, list):
                self._send_json({"error": "items must be an array"}, 400)
                return

            zip_bytes = export_items_to_zip(items, project_name, song_db=song_db)
            safe_name = re.sub(r"[^A-Za-z0-9._()-]+", "-", str(project_name or "bulletin")).strip("-")[:40] or "bulletin"
            filename = f"{safe_name}-propresenter.zip"

            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(zip_bytes)))
            self._cors_headers()
            self.end_headers()
            self.wfile.write(zip_bytes)
        except Exception as e:
            self._send_json({"error": f"Export failed: {e}"}, 500)

    def _handle_drive_upload(self):
        """Upload a file to Google Drive. Body: {filename, content (base64), mimeType}."""
        import base64 as _base64
        settings = _read_json(SETTINGS_FILE, {})
        auth = _google_auth_header()
        if not auth or not settings.get('googleDriveScopeGranted'):
            self._send_json({
                "error": "Google Drive not connected. Reconnect Google in Settings to enable Drive.",
            }, 401)
            return

        try:
            body = self._read_body_json()
        except Exception:
            self._send_json({"error": "Invalid JSON body."}, 400)
            return

        if not isinstance(body, dict):
            self._send_json({"error": "Invalid JSON body."}, 400)
            return

        filename    = (body.get('filename') or '').strip()
        content_b64 = (body.get('content')  or '').strip()
        mime_type   = (body.get('mimeType')  or 'application/octet-stream').strip()

        if not filename or not content_b64:
            self._send_json({"error": "Missing required fields: filename, content."}, 400)
            return

        try:
            file_bytes = _base64.b64decode(content_b64)
        except Exception:
            self._send_json({"error": "content must be base64-encoded."}, 400)
            return

        folder_id = (settings.get('googleDriveFolderId') or '').strip()

        # Build multipart/related body for Drive Files API v3
        boundary  = f'bulletin_generator_boundary_{id(self)}'
        metadata  = {"name": filename}
        if folder_id:
            metadata["parents"] = [folder_id]

        meta_json  = json.dumps(metadata).encode('utf-8')
        body_parts = (
            f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'
        ).encode() + meta_json + (
            f'\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n'
        ).encode() + file_bytes + f'\r\n--{boundary}--'.encode()

        url = 'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,webViewLink'

        def _do_upload(a):
            req = urllib.request.Request(
                url, data=body_parts,
                headers={
                    'Authorization': a,
                    'Content-Type':  f'multipart/related; boundary={boundary}',
                    'Content-Length': str(len(body_parts)),
                },
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())

        try:
            result = _do_upload(auth)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                new_auth = _refresh_google_token()
                if new_auth:
                    try:
                        result = _do_upload(new_auth)
                    except Exception as e2:
                        self._send_json({"error": f"Drive upload failed after token refresh: {e2}"}, 502)
                        return
                else:
                    self._send_json({
                        "error": "Google Drive token expired. Reconnect Google in Settings.",
                        "reconnectNeeded": True,
                    }, 401)
                    return
            else:
                err_body = ''
                try:
                    err_body = e.read().decode('utf-8', errors='replace')[:300]
                except Exception:
                    pass
                if e.code == 403:
                    self._send_json({
                        "error": "Google Drive permission denied. Check that the folder ID is correct and the account has write access.",
                        "code": "drive_permission_denied",
                        "detail": err_body,
                    }, 403)
                elif e.code == 404:
                    self._send_json({
                        "error": "Google Drive folder not found. Check the folder ID in Settings.",
                        "code": "drive_folder_not_found",
                        "detail": err_body,
                    }, 404)
                elif e.code == 400:
                    self._send_json({
                        "error": f"Google Drive rejected the upload request: {err_body}",
                        "code": "drive_bad_request",
                        "detail": err_body,
                    }, 400)
                else:
                    self._send_json({"error": f"Drive API returned HTTP {e.code}: {err_body}"}, 502)
                return
        except Exception as e:
            self._send_json({"error": f"Drive upload failed: {e}"}, 500)
            return

        self._send_json({
            "ok":      True,
            "fileId":  result.get("id"),
            "fileUrl": result.get("webViewLink"),
            "filename": filename,
        })

    def _apply_update_server(self):
        """Trigger Watchtower to pull the latest image and restart the container."""
        try:
            req = urllib.request.Request(
                WATCHTOWER_URL,
                data=b"",
                headers={
                    "Authorization": f"Bearer {WATCHTOWER_TOKEN}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            self._send_json({
                "ok": True,
                "mode": "server",
                "message": "Update triggered. The server will pull the new image and restart — this usually takes 1–3 minutes.",
                "watchtowerResponse": body[:200] if body else None,
            })
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            self._send_json({
                "error": f"Watchtower returned HTTP {e.code}. Check that WATCHTOWER_TOKEN matches in docker-compose.yml.",
                "detail": body,
                "manualFallback": "SSH into your server and run: docker compose pull && docker compose up -d",
            }, 502)
        except urllib.error.URLError as e:
            self._send_json({
                "error": f"Could not reach Watchtower at {WATCHTOWER_URL}. Is the watchtower service running?",
                "detail": str(e.reason),
                "manualFallback": "SSH into your server and run: docker compose pull && docker compose up -d",
            }, 502)
        except Exception as e:
            self._send_json({
                "error": f"Unexpected error triggering update: {e}",
                "manualFallback": "SSH into your server and run: docker compose pull && docker compose up -d",
            }, 500)

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
                    Path(tmp_zip).unlink(missing_ok=True)
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
                if result is None:
                    # None means auth failure (401/403) — refresh token and retry once
                    new_auth = _refresh_google_token()
                    if new_auth:
                        result = fetch_google_cal_events(new_auth, google_cal_ids, exclude)
                    else:
                        result = []
            else:
                result = fetch_and_parse_calendars(urls, exclude)

            if result is None:
                payload = {'ok': False, 'events': [], 'error': 'All calendar fetches failed.'}
            else:
                payload = {'ok': True, 'events': result}

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            # Only cache successful responses — failures must not be cached so that a
            # token refresh on the next request has a chance to succeed immediately.
            cache_ctrl = 'max-age=900' if payload['ok'] else 'no-store'
            self.send_header('Cache-Control', cache_ctrl)
            self._cors_headers()
            self.end_headers()
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
    _initialize_local_file(TEMPLATES_FILE, TEMPLATES_EXAMPLE_FILE, [])
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
