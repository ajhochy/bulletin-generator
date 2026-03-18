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
import socket
import threading
import webbrowser

DESKTOP_PORT = 8765

# Set desktop mode before importing server
os.environ.setdefault('APP_MODE', 'desktop')

# Load PCO OAuth credentials bundled with the desktop build
def _load_desktop_config():
    try:
        import desktop_config
        os.environ.setdefault('PCO_CLIENT_ID',     desktop_config.PCO_CLIENT_ID)
        os.environ.setdefault('PCO_CLIENT_SECRET', desktop_config.PCO_CLIENT_SECRET)
    except ImportError:
        pass  # Credentials not bundled — OAuth connect will show an error

_load_desktop_config()


def _wait_for_server(port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main():
    import server

    t = threading.Thread(target=server.run_server, args=(DESKTOP_PORT,), daemon=True)
    t.start()

    if _wait_for_server(DESKTOP_PORT):
        webbrowser.open(f'http://localhost:{DESKTOP_PORT}/')
    else:
        print(f'Bulletin Generator failed to start on port {DESKTOP_PORT}.')
        print('Make sure no other app is using that port and try again.')
        sys.exit(1)

    # Keep the process alive until the server thread ends
    t.join()


if __name__ == '__main__':
    main()
