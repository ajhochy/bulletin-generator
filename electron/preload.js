/**
 * Electron preload script for Bulletin Generator.
 *
 * contextIsolation is enabled and nodeIntegration is disabled in the
 * BrowserWindow webPreferences, so this script runs in an isolated context
 * that has access to Node/Electron APIs but cannot leak them into the
 * renderer's global scope unless explicitly bridged via contextBridge.
 *
 * The current app architecture has no IPC needs (the renderer talks directly
 * to the Python sidecar over HTTP). This file is therefore intentionally
 * minimal — it exists to satisfy Electron's preload contract and to serve
 * as the safe extension point if IPC is added in a future issue.
 */

// No APIs are exposed to the renderer at this time.
// If you need to expose a capability, use contextBridge.exposeInMainWorld():
//
//   import { contextBridge, ipcRenderer } from 'electron';
//   contextBridge.exposeInMainWorld('electronAPI', {
//     exampleMethod: () => ipcRenderer.invoke('example'),
//   });
