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
import threading
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR  = Path(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

PROJECTS_FILE      = DATA_DIR / "projects.json"
ANNOUNCEMENTS_FILE = DATA_DIR / "announcements.json"
SETTINGS_FILE      = DATA_DIR / "settings.json"
PROJECTS_EXAMPLE_FILE      = DATA_DIR / "projects.example.json"
ANNOUNCEMENTS_EXAMPLE_FILE = DATA_DIR / "announcements.example.json"
SETTINGS_EXAMPLE_FILE      = DATA_DIR / "settings.example.json"

PCO_BASE    = 'https://api.planningcenteronline.com/services/v2'
DEFAULT_EXCLUDE = ['sunday morning worship', 'sunday service', 'worship service']


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
    app_id = os.environ.get("PCO_APP_ID", "").strip()
    secret = os.environ.get("PCO_SECRET", "").strip()
    if not app_id or not secret:
        return None
    token = base64.b64encode(f"{app_id}:{secret}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _public_config():
    return {
        "pcoConfigured": _pco_auth_header() is not None,
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

    # ── Helpers ────────────────────────────────────────────────────────────────

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

        if path == "/":
            self.path = "/worship-booklet.html"
            super().do_GET()
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

        if path == "/api/bootstrap":
            settings = _read_json(SETTINGS_FILE, {})
            self._send_json({
                "settings": settings,
                "config": _public_config(),
            })
            return

        if self.path.startswith("/pco-proxy/"):
            self._proxy_pco()
            return

        if self.path.startswith("/cal"):
            self._handle_cal()
            return

        super().do_GET()

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
                    projects[idx] = project
                else:
                    projects.append(project)
                _write_json(PROJECTS_FILE, projects)
            self._send_json({"ok": True})
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

        if path == "/api/pdf":
            self._handle_pdf()
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
                    "--paper-width=5.5",
                    "--paper-height=8.5",
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

        try:
            with urllib.request.urlopen(req) as resp:
                data = resp.read()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors_headers()
            self.end_headers()
            self.wfile.write(data)
        except urllib.error.HTTPError as e:
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

if __name__ == '__main__':
    _initialize_local_file(PROJECTS_FILE, PROJECTS_EXAMPLE_FILE, [])
    _initialize_local_file(ANNOUNCEMENTS_FILE, ANNOUNCEMENTS_EXAMPLE_FILE, [])
    _initialize_local_file(SETTINGS_FILE, SETTINGS_EXAMPLE_FILE, {})
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    os.chdir(str(BASE_DIR))
    server = http.server.ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print(f'  Worship Booklet Generator running at:')
    print(f'  http://localhost:{port}/')
    print(f'  Data directory: {DATA_DIR}')
    print(f'  PCO configured: {"yes" if _public_config()["pcoConfigured"] else "no"}')
    print(f'\n  Press Ctrl+C to stop.\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Server stopped.')
        server.server_close()
