/**
 * Electron preload script for Bulletin Generator.
 *
 * contextIsolation is enabled and nodeIntegration is disabled in the
 * BrowserWindow webPreferences, so this script runs in an isolated context
 * that has access to Node/Electron APIs but cannot leak them into the
 * renderer's global scope unless explicitly bridged via contextBridge.
 *
 * Exposed APIs:
 *   window.electronAuth — auth deep-link bridge (issue 013)
 *     .onCallback(cb)  Register a callback that fires when a
 *                      bulletingen://auth-callback deep link is received.
 *                      cb receives { url: string }.
 *                      Returns an unsubscribe function.
 *
 *   window.electronAPI — PDF generation bridge (issue 012)
 *     .generatePdf({ html, pageWidth, pageHeight, filename })
 *       → Promise<string>  (absolute path to the written PDF temp file)
 */

import { contextBridge, ipcRenderer } from 'electron';

// ── Auth deep-link bridge ─────────────────────────────────────────────────────
contextBridge.exposeInMainWorld('electronAuth', {
  onCallback(cb) {
    const handler = (_event, data) => cb(data);
    ipcRenderer.on('auth:callback', handler);
    return () => ipcRenderer.removeListener('auth:callback', handler);
  },
});

// ── PDF generation bridge ─────────────────────────────────────────────────────
contextBridge.exposeInMainWorld('electronAPI', {
  generatePdf: (opts) => ipcRenderer.invoke('pdf:generate', opts),
});
