/**
 * Electron main process for Bulletin Generator desktop app.
 *
 * Responsibilities:
 *   1. Spawn server.py as a sidecar on port 8765.
 *   2. Open a BrowserWindow pointing at http://localhost:8765 once the
 *      server is ready.
 *   3. Show a tray icon with a "Quit" menu item.
 *   4. Kill the sidecar cleanly on app quit.
 *   5. Show an error dialog and quit if the sidecar crashes.
 *   6. Register the `bulletingen` custom URL protocol and forward deep-link
 *      auth callbacks (bulletingen://auth-callback#...) to the renderer via
 *      IPC so Supabase can complete OAuth / magic-link sign-in.
 *
 * Port 8765 matches the existing desktop default so PCO OAuth redirect URIs
 * (http://localhost:8765/oauth/pco/callback) require no change.
 */

import { app, BrowserWindow, Tray, Menu, dialog, nativeImage } from 'electron';
import { spawn } from 'child_process';
import path from 'path';
import http from 'http';
import fs from 'fs';
import { fileURLToPath } from 'url';

// ESM equivalents for __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ── Constants ─────────────────────────────────────────────────────────────────

const PORT = 8765;
const APP_URL = `http://localhost:${PORT}/`;
const READY_TIMEOUT_MS = 20_000; // 20 s to wait for server to start
const READY_POLL_INTERVAL_MS = 200;

// ── Sidecar resolution ────────────────────────────────────────────────────────

/**
 * Return the command + args to launch the Python server.
 *
 * Packaged mode (process.resourcesPath exists and contains a `server` binary):
 *   The PyInstaller-produced `server` executable lives at
 *   <app>.app/Contents/Resources/server
 *
 * Dev mode (running via `electron .` from the repo root):
 *   Spawn `python3 server.py` relative to the repo root (__dirname/../).
 */
function resolveSidecar() {
  // Packaged: resourcesPath points to <app>.app/Contents/Resources/
  const packagedBin = path.join(process.resourcesPath, 'server');
  if (process.resourcesPath && fs.existsSync(packagedBin)) {
    return { cmd: packagedBin, args: [] };
  }

  // Dev: repo root is one directory above electron/
  const repoRoot = path.resolve(__dirname, '..');
  return {
    cmd: 'python3',
    args: [path.join(repoRoot, 'server.py'), String(PORT)],
  };
}

// ── Server-ready probe ────────────────────────────────────────────────────────

/**
 * Poll http://localhost:PORT/ until a 2xx/3xx response or timeout.
 * Returns a Promise that resolves when the server is up.
 */
function waitForServer(timeoutMs) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;

    function probe() {
      const req = http.get(APP_URL, (res) => {
        res.resume(); // drain
        resolve();
      });
      req.on('error', () => {
        if (Date.now() >= deadline) {
          reject(new Error(`Server did not start within ${timeoutMs / 1000}s`));
        } else {
          setTimeout(probe, READY_POLL_INTERVAL_MS);
        }
      });
      req.setTimeout(500, () => req.destroy());
    }

    probe();
  });
}

// ── Auth deep-link handling ───────────────────────────────────────────────────

/**
 * Register `bulletingen` as this app's custom URL protocol so the OS routes
 * bulletingen://auth-callback#... links here after OAuth/magic-link redirects.
 *
 * Must be called before app.whenReady() so it takes effect on first launch.
 * On Windows this also ensures single-instance behaviour (see second-instance
 * handler below).
 */
app.setAsDefaultProtocolClient('bulletingen');

/**
 * Extract the raw deep-link URL from a process.argv array.
 * On Windows, Electron relaunches a second instance with the protocol URL as
 * the last command-line argument when the app is already running.
 */
function extractDeepLinkUrl(argv) {
  return argv.find((arg) => arg.startsWith('bulletingen://')) || null;
}

/**
 * Forward a deep-link URL to the renderer window via IPC.
 * The preload script exposes window.electronAuth.onCallback so auth-ui.js
 * can call supabase.auth.setSession / exchangeCodeForSession.
 */
function handleDeepLink(url) {
  if (!url) return;
  if (mainWindow) {
    mainWindow.focus();
    mainWindow.webContents.send('auth:callback', { url });
  }
}

// ── State ─────────────────────────────────────────────────────────────────────

let mainWindow = null;
let tray = null;
let sidecar = null;
let sidecarExited = false; // flag so quit-handler doesn't double-kill

// ── Sidecar lifecycle ─────────────────────────────────────────────────────────

function spawnSidecar() {
  const { cmd, args } = resolveSidecar();

  const env = Object.assign({}, process.env, {
    APP_MODE: 'desktop',
    PORT: String(PORT),
  });

  sidecar = spawn(cmd, args, {
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  sidecar.stdout.on('data', (data) => {
    process.stdout.write(`[server] ${data}`);
  });

  sidecar.stderr.on('data', (data) => {
    process.stderr.write(`[server] ${data}`);
  });

  sidecar.on('exit', (code, signal) => {
    if (sidecarExited) return; // expected quit-path
    sidecarExited = true;

    const detail = signal
      ? `Signal: ${signal}`
      : `Exit code: ${code}`;

    dialog.showErrorBox(
      'Bulletin Generator — Server Error',
      `The background server stopped unexpectedly.\n${detail}\n\nThe app will now quit.`
    );
    app.quit();
  });
}

function killSidecar() {
  if (sidecar && !sidecarExited) {
    sidecarExited = true;
    sidecar.kill('SIGTERM');
  }
}

// ── Window ────────────────────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 900,
    title: 'Bulletin Generator',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadURL(APP_URL);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── Tray ──────────────────────────────────────────────────────────────────────

function createTray() {
  // Use the repo-level menubar icon if available; fall back to empty image.
  const iconPath = path.resolve(__dirname, '..', 'menubar-icon.png');
  const icon = fs.existsSync(iconPath)
    ? nativeImage.createFromPath(iconPath)
    : nativeImage.createEmpty();

  tray = new Tray(icon);
  tray.setToolTip('Bulletin Generator');

  const menu = Menu.buildFromTemplate([
    {
      label: 'Open Bulletin Generator',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
        } else {
          createWindow();
        }
      },
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => app.quit(),
    },
  ]);

  tray.setContextMenu(menu);
  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.show();
    } else {
      createWindow();
    }
  });
}

// ── App lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  spawnSidecar();

  try {
    await waitForServer(READY_TIMEOUT_MS);
  } catch (err) {
    dialog.showErrorBox(
      'Bulletin Generator — Startup Timeout',
      `${err.message}\n\nThe app will now quit.`
    );
    killSidecar();
    app.quit();
    return;
  }

  createWindow();
  createTray();
});

app.on('window-all-closed', () => {
  // On macOS it is conventional to keep the app running in the tray when all
  // windows are closed — do NOT quit here.
  // On other platforms, quit when all windows are gone.
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  // macOS: re-open the window when the dock/tray icon is clicked and no
  // windows are open.
  if (mainWindow === null) {
    createWindow();
  }
});

app.on('before-quit', () => {
  killSidecar();
});

// ── Deep-link auth callbacks ──────────────────────────────────────────────────

// macOS: the OS sends bulletingen:// URLs to an already-running instance via
// the 'open-url' event on the app object.
app.on('open-url', (event, url) => {
  event.preventDefault();
  handleDeepLink(url);
});

// Windows / Linux: Electron relaunches a second instance with the protocol URL
// appended to argv.  Request single-instance lock so the second instance
// hands its argv to the first instance and exits immediately.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  // This is the second instance — quit after passing the URL via the lock.
  app.quit();
}

app.on('second-instance', (_event, argv) => {
  // The first instance receives the second instance's argv here.
  const url = extractDeepLinkUrl(argv);
  if (url) handleDeepLink(url);

  // Also bring the window to front on Windows.
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});
