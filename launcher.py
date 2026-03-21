#!/usr/bin/env python3
"""
Desktop launcher for Bulletin Generator.
Starts the local server on a fixed port and opens the app in the default browser.

Desktop mode always uses port 8765 so the PCO OAuth redirect URI is predictable.
Register this in your PCO developer app:
  http://localhost:8765/oauth/pco/callback
"""

import os
import sys
import time
import signal
import socket
import threading
import webbrowser

DESKTOP_PORT = 8765


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
        return True  # Port is free

    my_pid = os.getpid()
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
        # Can't identify the process — wait briefly and hope it dies
        time.sleep(2)
        return not _port_in_use(port)

    # SIGTERM all targets
    for pid in targets:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    # Wait for port to free (up to 8 seconds)
    for _ in range(40):
        time.sleep(0.2)
        if not _port_in_use(port):
            return True

    # Escalate to SIGKILL
    for pid in targets:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    # Final wait after SIGKILL (up to 2 seconds)
    for _ in range(10):
        time.sleep(0.2)
        if not _port_in_use(port):
            return True

    return False  # Couldn't free the port


def _write_pid_file():
    """Write current PID so future launches can kill us."""
    try:
        pid_file = _get_pid_file()
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
    except OSError:
        pass

# Set desktop mode before importing server
os.environ.setdefault('APP_MODE', 'desktop')

# Load PCO OAuth credentials bundled with the desktop build
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


def _wait_for_server(port, timeout=15):
    """Wait for OUR new server to start listening."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _is_our_server(port):
    """Check if our Bulletin Generator server is already running on the port."""
    try:
        import http.client
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
        conn.request('GET', '/api/bootstrap')
        resp = conn.getresponse()
        body = resp.read().decode('utf-8', errors='replace')
        conn.close()
        return 'appMode' in body
    except Exception:
        return False


def _start_server_detached():
    """Start the server as a detached background process that survives app exit."""
    import subprocess

    # Find the real Python/executable path
    exe = sys.executable
    script_dir = os.path.dirname(os.path.abspath(__file__))
    server_script = os.path.join(script_dir, 'server.py')

    # For PyInstaller bundled app, run server in-process but forked
    pid = os.fork()
    if pid == 0:
        # Child process — become the background server
        os.setsid()  # Detach from parent session
        # Close inherited file descriptors
        try:
            devnull = os.open(os.devnull, os.O_RDWR)
            os.dup2(devnull, 0)
            os.dup2(devnull, 1)
            os.dup2(devnull, 2)
            os.close(devnull)
        except OSError:
            pass

        # Write PID file for the server process
        _write_pid_file()

        import server
        server.run_server(DESKTOP_PORT)
        sys.exit(0)
    else:
        # Parent process — return immediately so the .app exits
        return pid


def main():
    # If our server is already running, just open the browser and exit
    if _port_in_use(DESKTOP_PORT) and _is_our_server(DESKTOP_PORT):
        webbrowser.open(f'http://localhost:{DESKTOP_PORT}/')
        return

    # Something else is on our port — kill it
    if _port_in_use(DESKTOP_PORT):
        port_free = _kill_stale_server(DESKTOP_PORT)
        if not port_free:
            pass  # Try anyway — SO_REUSEADDR might save us

    # Start server as a detached background process
    _start_server_detached()

    # Wait for server to come up, then open browser
    if _wait_for_server(DESKTOP_PORT):
        webbrowser.open(f'http://localhost:{DESKTOP_PORT}/')
    else:
        print(f'Bulletin Generator failed to start on port {DESKTOP_PORT}.')
        print('Make sure no other app is using that port and try again.')
        sys.exit(1)

    # Parent exits — the .app closes, but the server keeps running in background


if __name__ == '__main__':
    main()
