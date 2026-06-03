/**
 * Electron preload script for Bulletin Generator.
 *
 * contextIsolation is enabled and nodeIntegration is disabled in the
 * BrowserWindow webPreferences, so this script runs in an isolated context
 * that has access to Node/Electron APIs but cannot leak them into the
 * renderer's global scope unless explicitly bridged via contextBridge.
 *
 * Exposed surface (window.electronAPI):
 *   generatePdf({ html, pageWidth, pageHeight, filename })
 *     → Promise<string>  (absolute path to the written PDF temp file)
 *     Delegates to the 'pdf:generate' IPC handler in main.js which uses
 *     webContents.printToPDF() — no headless Chrome required.
 *     Only present when running inside Electron; call sites should guard with
 *       if (window.electronAPI?.generatePdf) { ... }
 */

import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  /**
   * Generate a PDF from print-ready HTML using Electron's built-in renderer.
   *
   * @param {object} opts
   * @param {string} opts.html        - Complete HTML document to render.
   * @param {number} [opts.pageWidth=5.5]   - Page width in inches.
   * @param {number} [opts.pageHeight=8.5]  - Page height in inches.
   * @param {string} [opts.filename='bulletin.pdf'] - Desired output filename.
   * @returns {Promise<string>} Absolute path to the generated PDF temp file.
   */
  generatePdf: (opts) => ipcRenderer.invoke('pdf:generate', opts),
});
