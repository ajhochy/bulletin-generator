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
 */

import { contextBridge, ipcRenderer } from 'electron';

// ── Auth deep-link bridge ─────────────────────────────────────────────────────
//
// The main process sends 'auth:callback' with { url } when a
// bulletingen://auth-callback#access_token=...&refresh_token=... deep link
// is opened.  auth-ui.js registers via window.electronAuth.onCallback and
// calls supabase.auth.setSession / exchangeCodeForSession.

contextBridge.exposeInMainWorld('electronAuth', {
  /**
   * Register a listener for Supabase auth deep-link callbacks.
   *
   * @param {function({ url: string }): void} cb
   * @returns {function(): void} unsubscribe — call to remove the listener
   */
  onCallback(cb) {
    const handler = (_event, data) => cb(data);
    ipcRenderer.on('auth:callback', handler);
    return () => ipcRenderer.removeListener('auth:callback', handler);
  },
});
