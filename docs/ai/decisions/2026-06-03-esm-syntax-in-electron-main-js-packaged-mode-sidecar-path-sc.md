---
date: 2026-06-03
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# ESM syntax in `electron/main.js`; packaged-mode sidecar path scaffolded early

**Context.** Root `package.json` has `"type": "module"`, making Node treat all `.js` files in the tree as ESM. Electron 28+ supports ESM main entry points. The alternative — CJS `require()` in `main.js` — would require either a `.cjs` extension or a local `package.json` override in `electron/` (neither is wrong, but both add complexity).

**Decision.** Use ESM `import` syntax in `electron/main.js` and `electron/preload.js`. Requires the `fileURLToPath(import.meta.url)` pattern to derive `__dirname` in ESM context.

**Packaged-mode path.** `resolveSidecar()` in `main.js` probes `process.resourcesPath + '/server'` for the PyInstaller binary. The binary doesn't exist until issue 014 (packaging). Scaffolding the path now means issue 014 only needs to place the binary — no main-process changes required.

**Consequences.**
- Issue 014 (packaging) can focus on PyInstaller spec changes and `electron-builder` config; `main.js` path logic is already correct.
- If Electron's ESM support has edge-cases in the packaged `.asar` context, fall back to `electron/main.cjs` with `require()` + an `electron/` local `package.json` override.
