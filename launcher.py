#!/usr/bin/env python3
"""
Desktop launcher for Bulletin Generator.
Starts the local server on a fixed port and runs as a macOS menu bar app.

Desktop mode always uses port 8765 so the PCO OAuth redirect URI is predictable.
Register this in your PCO developer app:
  http://localhost:8765/oauth/pco/callback
"""

import os
import subprocess
import sys
import time
import signal
import socket
import threading
import webbrowser

DESKTOP_PORT = 8765
APP_URL      = f'http://localhost:{DESKTOP_PORT}/'


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_pid_file():
    """Return path to the PID file in the data directory."""
    home = os.path.expanduser('~')
    data_dir = os.path.join(home, 'Documents', 'bulletin-generator-data')
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, 'server.pid')


def _port_in_use(port):
    """Check if something is listening on the port."""
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return True
    except OSError:
        return False


def _kill_stale_server(port):
    """Kill any leftover process holding our port from a previous run.
    Returns only after the port is confirmed free or all attempts exhausted."""
    if not _port_in_use(port):
        return True

    my_pid  = os.getpid()
    targets = set()

    # Strategy 1: PID file from previous run
    pid_file = _get_pid_file()
    try:
        with open(pid_file, 'r') as f:
            old_pid = int(f.read().strip())
        if old_pid != my_pid:
            targets.add(old_pid)
    except (FileNotFoundError, ValueError, OSError):
        pass

    # Strategy 2: lsof fallback
    import subprocess
    for lsof_path in ['/usr/sbin/lsof', '/usr/bin/lsof', 'lsof']:
        try:
            result = subprocess.run(
                [lsof_path, '-ti', f':{port}'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for pid_str in result.stdout.strip().split('\n'):
                    if pid_str:
                        pid = int(pid_str)
                        if pid != my_pid:
                            targets.add(pid)
                break
        except Exception:
            continue

    if not targets:
        time.sleep(2)
        return not _port_in_use(port)

    for pid in targets:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    for _ in range(40):
        time.sleep(0.2)
        if not _port_in_use(port):
            return True

    for pid in targets:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    for _ in range(10):
        time.sleep(0.2)
        if not _port_in_use(port):
            return True

    return False


def _write_pid_file():
    """Write current PID so future launches can kill us."""
    try:
        with open(_get_pid_file(), 'w') as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def _wait_for_server(port, timeout=15):
    """Wait for our new server to start listening."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _is_our_server_current_version(port):
    """Return True only if a Bulletin Generator server at this port is running
    the same APP_VERSION as this build.  Forces a restart on version mismatch."""
    try:
        import http.client, json as _json
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
        conn.request('GET', '/api/bootstrap')
        resp = conn.getresponse()
        body = resp.read().decode('utf-8', errors='replace')
        conn.close()
        data = _json.loads(body)
        running_version = (data.get('config') or {}).get('appVersion', '')
        this_version    = os.environ.get('APP_VERSION', '1.09').lstrip('v')
        return bool(running_version) and running_version == this_version
    except Exception:
        return False


def _icon_path():
    """Return path to the menu bar icon bundled with the app."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'menubar-icon.png')


# ── Desktop config ─────────────────────────────────────────────────────────────

# Set desktop mode before importing server
os.environ.setdefault('APP_MODE', 'desktop')


def _load_desktop_config():
    try:
        import desktop_config
        os.environ.setdefault('PCO_CLIENT_ID',     desktop_config.PCO_CLIENT_ID)
        os.environ.setdefault('PCO_CLIENT_SECRET', desktop_config.PCO_CLIENT_SECRET)
        if hasattr(desktop_config, 'GOOGLE_CLIENT_ID'):
            os.environ.setdefault('GOOGLE_CLIENT_ID',     desktop_config.GOOGLE_CLIENT_ID)
        if hasattr(desktop_config, 'GOOGLE_CLIENT_SECRET'):
            os.environ.setdefault('GOOGLE_CLIENT_SECRET', desktop_config.GOOGLE_CLIENT_SECRET)
    except ImportError:
        pass  # Credentials not bundled — OAuth connect will show an error


_load_desktop_config()


# ── Menu bar app ───────────────────────────────────────────────────────────────

def _make_menu_bar_app():
    import rumps

    class _App(rumps.App):
        def __init__(self):
            super().__init__('', icon=_icon_path(), template=True, quit_button=None)
            self.menu = [
                rumps.MenuItem('Open in Browser', callback=self._open),
                None,  # separator
                rumps.MenuItem('Quit', callback=self._quit),
            ]

        def _open(self, _):
            try:
                subprocess.Popen(['open', '-a', 'Google Chrome', APP_URL])
            except Exception:
                webbrowser.open(APP_URL)

        def _quit(self, _):
            rumps.quit_application()

    return _App()


# ── Server thread ──────────────────────────────────────────────────────────────

def _start_server_thread():
    """Run the server in a daemon thread (dies automatically when the process exits)."""
    import server
    t = threading.Thread(target=server.run_server, args=(DESKTOP_PORT,), daemon=True)
    t.start()
    return t


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    # If our server is already running at the correct version, another instance
    # owns the menu bar — just open the browser and exit to avoid duplicates.
    if _port_in_use(DESKTOP_PORT) and _is_our_server_current_version(DESKTOP_PORT):
        webbrowser.open(APP_URL)
        return

    # Kill anything on our port (old version, stale process, or unrelated app).
    if _port_in_use(DESKTOP_PORT):
        _kill_stale_server(DESKTOP_PORT)

    # Start server in a background thread and record the PID
    _start_server_thread()
    _write_pid_file()

    # Wait for the server to come up
    if not _wait_for_server(DESKTOP_PORT):
        import rumps
        rumps.alert(
            title='Bulletin Generator',
            message=f'Failed to start the local server on port {DESKTOP_PORT}.\n'
                    'Make sure no other app is using that port and try again.',
        )
        sys.exit(1)

    # Open browser, then hand control to the menu bar run loop
    webbrowser.open(APP_URL)
    _make_menu_bar_app().run()


if __name__ == '__main__':
    main()
