# E2E Playwright Suite — Phase 1 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a trustworthy two-lane Playwright harness against the real `server.py` + real hosted Supabase, ending in one green end-to-end smoke test in both the deterministic (core) and live lanes, wired into CI.

**Architecture:** Playwright drives the real frontend served by a real `server.py` running in server mode (`APP_MODE=server`, port 8080). Auth is Supabase Bearer-JWT. A "setup" Playwright project provisions an isolated ephemeral Supabase user+workspace (via `service_role`) for the core lane and signs in as `worship@visaliacrc.com` for the live lane, each saving a `storageState`. A matching "teardown" project deletes the ephemeral identity. Determinism comes from Playwright's `page.clock`. This phase delivers the harness + smoke only; exhaustive coverage is later phases.

**Tech Stack:** `@playwright/test` (TypeScript), `@supabase/supabase-js` (already a dependency), Python 3 `server.py`, hosted Supabase Postgres, GitHub Actions.

**Reference spec:** `docs/superpowers/specs/2026-06-05-e2e-playwright-suite-design.md`

---

## Key facts (verified against source — do not re-derive)

- Boot: `python3 server.py` runs server mode by default. `APP_MODE` (server.py:256) defaults to `"server"`; server binds `0.0.0.0:8080` via `run_server(port=8080)` (server.py:3359).
- Server-mode required env: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` (validated server.py:268–286).
- Auth: client sends `Authorization: Bearer <access_token>`; `apiFetch` attaches it from the supabase-js session (api.js:3–26, line 7). Server verifies via `auth.authenticate_authorization_header` (auth.py:287).
- `/api/me` server-mode 200 body: `{"mode":"server","user_id","email","workspace_id","role"}`; 401 when unauthenticated.
- Supabase config injected at `GET /src/js/supabase-config.js` as `globalThis.BULLETIN_SUPABASE_CONFIG = {url, anonKey}` (server.py:1376).
- Workspace provisioning is **domain-allow-list gated** (`provision_first_login`, auth.py:203–284). Arbitrary new users get **403, no workspace**. Therefore ephemeral test identities MUST be created directly via `service_role` (create user + workspace + `workspace_members` row), not via normal login.
- Tables (migrations `supabase/migrations/20260602000001_*` and `_002_*`): `profiles(id,email,display_name)`, `workspaces(id,name,slug,created_by_user_id)`, `workspace_members(workspace_id,user_id,role)` PK `(workspace_id,user_id)`, `projects(id TEXT,workspace_id,owner_user_id,visibility,state JSONB,revision)`, plus `workspace_settings`, `user_settings`, `announcements`, `songs`, `templates`, `fonts`.
- Item rows already render `data-idx` and `data-action="up|down|delete|collapse"` (editor.js:112–124). Other row types need a consistent `data-testid` convention added.
- Existing tests: `vitest` + jsdom, config in `vite.config.js`, setup `vitest.setup.js`. Leave entirely intact.

---

## File structure (created this phase)

- `playwright.config.ts` — two lanes (core, live) + setup/teardown projects, `webServer` spawns `python3 server.py`.
- `tsconfig.e2e.json` — TS config scoped to `tests/e2e`.
- `.env.e2e.example` — documents required test env vars (committed); `.env.e2e` is gitignored.
- `tests/e2e/helpers/env.ts` — load + validate test env.
- `tests/e2e/helpers/supabase-admin.ts` — service_role client; create/seed/delete ephemeral identity.
- `tests/e2e/helpers/auth.setup.ts` — core + live setup specs (provision/sign-in, save storageState).
- `tests/e2e/helpers/auth.teardown.ts` — delete ephemeral identity.
- `tests/e2e/helpers/clock.ts` — `page.clock` wrappers for the known debounces/timers.
- `tests/e2e/helpers/pdf.ts` — assert a Buffer is a valid PDF.
- `tests/e2e/pages/AppShell.ts` — minimal page object: tab switching + readiness.
- `tests/e2e/flows/smoke.spec.ts` — the end-to-end smoke (tagged `@core` and a `@live` variant).
- `.github/workflows/e2e-core.yml` — PR-blocking core lane.
- `.github/workflows/e2e-live.yml` — nightly/dispatch live lane.
- Modified: `package.json` (scripts + devDeps), `.gitignore`, render sites for `data-testid`.

---

### Task 1: Install Playwright test runner and add scripts

**Files:**
- Modify: `package.json`
- Modify: `.gitignore`

- [ ] **Step 1: Add the test runner and scripts**

Run:
```bash
npm install -D @playwright/test@^1.59.1 dotenv@^16.4.5
npx playwright install --with-deps chromium
```

- [ ] **Step 2: Add npm scripts to `package.json`**

Add these keys to the existing `"scripts"` object (keep `test`/`test:watch` unchanged):
```json
"test:e2e": "playwright test --project=core",
"test:e2e:live": "playwright test --project=live",
"test:e2e:ui": "playwright test --ui",
"test:e2e:report": "playwright show-report"
```

- [ ] **Step 3: Ignore generated + secret artifacts**

Append to `.gitignore`:
```
# Playwright E2E
/.env.e2e
/test-results/
/playwright-report/
/tests/e2e/.auth/
/tests/e2e/recordings/*.local.har
```

- [ ] **Step 4: Verify the runner is available**

Run: `npx playwright --version`
Expected: prints `Version 1.59.x`.

- [ ] **Step 5: Commit**

```bash
git add package.json package-lock.json .gitignore
git commit -m "test(e2e): add @playwright/test runner and scripts"
```

---

### Task 2: Test env contract

**Files:**
- Create: `.env.e2e.example`
- Create: `tests/e2e/helpers/env.ts`
- Create: `tsconfig.e2e.json`

- [ ] **Step 1: Document required env (committed example)**

Create `.env.e2e.example`:
```bash
# Hosted Supabase TEST project (never production)
SUPABASE_URL=https://YOUR_TEST_REF.supabase.co
SUPABASE_ANON_KEY=eyJ...anon...
SUPABASE_JWT_SECRET=your-test-jwt-secret
SUPABASE_SERVICE_ROLE_KEY=eyJ...service_role...   # setup/teardown only
DATABASE_URL=postgresql://postgres:pw@db.YOUR_TEST_REF.supabase.co:5432/postgres

# Live lane only — the already-connected workspace account
E2E_LIVE_EMAIL=worship@visaliacrc.com
E2E_LIVE_PASSWORD=...

# Optional: where the app is served during tests
E2E_BASE_URL=http://127.0.0.1:8080
```

- [ ] **Step 2: Write the failing test for env loading**

Create `tests/e2e/helpers/env.test.ts` (run with vitest):
```ts
import { describe, it, expect } from 'vitest';
import { loadE2eEnv } from './env';

describe('loadE2eEnv', () => {
  it('throws a clear error when a required var is missing', () => {
    expect(() => loadE2eEnv({}, ['SUPABASE_URL'])).toThrow(/SUPABASE_URL/);
  });
  it('returns the requested vars when present', () => {
    const env = loadE2eEnv({ SUPABASE_URL: 'x', SUPABASE_ANON_KEY: 'y' }, [
      'SUPABASE_URL',
      'SUPABASE_ANON_KEY',
    ]);
    expect(env).toEqual({ SUPABASE_URL: 'x', SUPABASE_ANON_KEY: 'y' });
  });
});
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `npx vitest run tests/e2e/helpers/env.test.ts`
Expected: FAIL — `Cannot find module './env'`.

- [ ] **Step 4: Implement `env.ts`**

Create `tests/e2e/helpers/env.ts`:
```ts
import { config as loadDotenv } from 'dotenv';

let loaded = false;
function ensureDotenv() {
  if (!loaded) {
    loadDotenv({ path: '.env.e2e' });
    loaded = true;
  }
}

export function loadE2eEnv<K extends string>(
  source: Record<string, string | undefined>,
  required: readonly K[],
): Record<K, string> {
  const out = {} as Record<K, string>;
  const missing: string[] = [];
  for (const key of required) {
    const val = source[key];
    if (!val) missing.push(key);
    else out[key] = val;
  }
  if (missing.length) {
    throw new Error(`Missing required E2E env var(s): ${missing.join(', ')}`);
  }
  return out;
}

export function e2eEnv<K extends string>(required: readonly K[]): Record<K, string> {
  ensureDotenv();
  return loadE2eEnv(process.env, required);
}
```

- [ ] **Step 5: Add a TS config for the suite**

Create `tsconfig.e2e.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "types": ["node"]
  },
  "include": ["tests/e2e/**/*.ts", "playwright.config.ts"]
}
```

- [ ] **Step 6: Run the env test to confirm it passes**

Run: `npx vitest run tests/e2e/helpers/env.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add .env.e2e.example tests/e2e/helpers/env.ts tests/e2e/helpers/env.test.ts tsconfig.e2e.json
git commit -m "test(e2e): add validated test env contract"
```

---

### Task 3: Supabase admin helper — provision & destroy an isolated identity

> The ephemeral identity is the core lane's isolation boundary. `service_role` bypasses RLS, so we create the user, a dedicated workspace, the membership row, and a defensive `profiles` upsert (works whether or not an `auth.users` trigger mirrors profiles).

**Files:**
- Create: `tests/e2e/helpers/supabase-admin.ts`

- [ ] **Step 1: Write the failing integration test**

Create `tests/e2e/helpers/supabase-admin.test.ts` (run with vitest; requires `.env.e2e` pointing at the TEST project):
```ts
import { describe, it, expect, afterAll } from 'vitest';
import { createEphemeralIdentity, destroyEphemeralIdentity, type EphemeralIdentity } from './supabase-admin';

const RUN = process.env.SUPABASE_SERVICE_ROLE_KEY ? describe : describe.skip;
let id: EphemeralIdentity;

RUN('ephemeral identity lifecycle', () => {
  it('creates a user + workspace + membership', async () => {
    id = await createEphemeralIdentity('lifecycle');
    expect(id.userId).toMatch(/^[0-9a-f-]{36}$/);
    expect(id.workspaceId).toMatch(/^[0-9a-f-]{36}$/);
    expect(id.email).toContain('@');
    expect(id.password.length).toBeGreaterThan(12);
  });
  afterAll(async () => { if (id) await destroyEphemeralIdentity(id); });
});
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `npx vitest run tests/e2e/helpers/supabase-admin.test.ts`
Expected: FAIL — `Cannot find module './supabase-admin'`.

- [ ] **Step 3: Implement `supabase-admin.ts`**

Create `tests/e2e/helpers/supabase-admin.ts`:
```ts
import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { randomUUID } from 'node:crypto';
import { e2eEnv } from './env';

export interface EphemeralIdentity {
  userId: string;
  workspaceId: string;
  email: string;
  password: string;
}

function admin(): SupabaseClient {
  const env = e2eEnv(['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY'] as const);
  return createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
}

/** Create an isolated user + workspace + owner membership. RLS-bypassing (service_role). */
export async function createEphemeralIdentity(label: string): Promise<EphemeralIdentity> {
  const sb = admin();
  const tag = randomUUID().slice(0, 8);
  const email = `e2e-${label}-${tag}@e2e.bulletin.test`;
  const password = `E2e-${randomUUID()}`;

  const { data: created, error: userErr } = await sb.auth.admin.createUser({
    email, password, email_confirm: true,
  });
  if (userErr || !created.user) throw new Error(`createUser failed: ${userErr?.message}`);
  const userId = created.user.id;

  // Defensive: ensure a profiles row exists regardless of trigger behavior.
  await sb.from('profiles').upsert({ id: userId, email }, { onConflict: 'id' });

  const { data: ws, error: wsErr } = await sb
    .from('workspaces')
    .insert({ name: `E2E ${tag}`, slug: `e2e-${tag}`, created_by_user_id: userId })
    .select('id')
    .single();
  if (wsErr || !ws) throw new Error(`workspace insert failed: ${wsErr?.message}`);
  const workspaceId = ws.id as string;

  const { error: memErr } = await sb
    .from('workspace_members')
    .insert({ workspace_id: workspaceId, user_id: userId, role: 'owner' });
  if (memErr) throw new Error(`membership insert failed: ${memErr.message}`);

  return { userId, workspaceId, email, password };
}

export async function destroyEphemeralIdentity(id: EphemeralIdentity): Promise<void> {
  const sb = admin();
  // FK cleanup first (workspace-scoped rows), then workspace, then auth user.
  await sb.from('projects').delete().eq('workspace_id', id.workspaceId);
  await sb.from('workspace_members').delete().eq('workspace_id', id.workspaceId);
  await sb.from('workspaces').delete().eq('id', id.workspaceId);
  await sb.auth.admin.deleteUser(id.userId);
}
```

- [ ] **Step 4: Run the lifecycle test against the test project**

Run: `npx vitest run tests/e2e/helpers/supabase-admin.test.ts`
Expected: PASS (creates + deletes a real user/workspace). If a column name differs from the migration, fix the literal here and re-run.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/helpers/supabase-admin.ts tests/e2e/helpers/supabase-admin.test.ts
git commit -m "test(e2e): add service_role helper to provision/destroy isolated identity"
```

---

### Task 4: Determinism helpers (page.clock wrappers)

**Files:**
- Create: `tests/e2e/helpers/clock.ts`

- [ ] **Step 1: Implement the clock helper**

Create `tests/e2e/helpers/clock.ts`:
```ts
import type { Page } from '@playwright/test';

/** App debounce/timer constants (verified in src/js). */
export const TIMERS = {
  previewDebounceMs: 250,
  persistDebounceMs: 350,
  presenceHeartbeatMs: 30_000,
  filesRefreshMs: 30_000,
  calCacheMs: 15 * 60 * 1000,
} as const;

/** Install a controllable clock. Call before navigation. */
export async function installClock(page: Page): Promise<void> {
  await page.clock.install();
}

/** Advance past the autosave debounce so a persist POST fires deterministically. */
export async function settlePersist(page: Page): Promise<void> {
  await page.clock.runFor(TIMERS.previewDebounceMs + TIMERS.persistDebounceMs + 50);
}

/** Advance one presence heartbeat interval. */
export async function tickPresence(page: Page): Promise<void> {
  await page.clock.runFor(TIMERS.presenceHeartbeatMs + 100);
}
```

- [ ] **Step 2: Typecheck the helper**

Run: `npx tsc -p tsconfig.e2e.json --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/helpers/clock.ts
git commit -m "test(e2e): add page.clock determinism helpers"
```

---

### Task 5: PDF assertion helper

**Files:**
- Create: `tests/e2e/helpers/pdf.ts`

- [ ] **Step 1: Write the failing test**

Create `tests/e2e/helpers/pdf.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { assertValidPdf } from './pdf';

describe('assertValidPdf', () => {
  it('accepts a minimal PDF buffer', () => {
    const buf = Buffer.from('%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF');
    expect(() => assertValidPdf(buf)).not.toThrow();
  });
  it('rejects non-PDF bytes', () => {
    expect(() => assertValidPdf(Buffer.from('<html></html>'))).toThrow(/not a PDF/i);
  });
  it('rejects an empty buffer', () => {
    expect(() => assertValidPdf(Buffer.alloc(0))).toThrow(/empty/i);
  });
});
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `npx vitest run tests/e2e/helpers/pdf.test.ts`
Expected: FAIL — `Cannot find module './pdf'`.

- [ ] **Step 3: Implement `pdf.ts`**

Create `tests/e2e/helpers/pdf.ts`:
```ts
/** Throws unless `buf` looks like a valid, non-empty PDF. Returns the page count (best-effort). */
export function assertValidPdf(buf: Buffer): number {
  if (!buf || buf.length === 0) throw new Error('PDF buffer is empty');
  const head = buf.subarray(0, 5).toString('latin1');
  if (head !== '%PDF-') throw new Error(`Buffer is not a PDF (header was "${head}")`);
  const tail = buf.subarray(-1024).toString('latin1');
  if (!tail.includes('%%EOF')) throw new Error('PDF is missing %%EOF trailer');
  const matches = buf.toString('latin1').match(/\/Type\s*\/Page[^s]/g);
  return matches ? matches.length : 0;
}
```

- [ ] **Step 4: Run it to confirm it passes**

Run: `npx vitest run tests/e2e/helpers/pdf.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/helpers/pdf.ts tests/e2e/helpers/pdf.test.ts
git commit -m "test(e2e): add PDF validity assertion helper"
```

---

### Task 6: Add `data-testid` convention to dynamic row renders

> Convention: every repeated row gets `data-testid="<area>-row"` plus a numeric `data-index`. Item cards already expose `data-idx`; we add `data-testid` alongside. Apply the SAME one-line pattern at each render site.

**Files:**
- Modify: `src/js/editor.js:112` (order-of-worship item card)
- Modify: `src/js/announcements.js` (announcement card render)
- Modify: `src/js/staff.js` (staff row render)
- Modify: `src/js/calendar.js` (calendar event row render)
- Modify: `src/js/songs.js` (song-db list item render)
- Modify: `src/js/editor.js` (welcome item render, volunteer-roles render — locate the row-creating element in each)

- [ ] **Step 1: Anchor example — item card (editor.js)**

At `src/js/editor.js:112`, immediately after `card.dataset.idx = idx;`, add:
```js
    card.dataset.testid = 'item-row';
    card.dataset.index = idx;
```

- [ ] **Step 2: Apply the same pattern to each other row render**

For each file above, find the element created per row (the `document.createElement(...)` whose result is appended to the list container) and add the two lines, substituting the area name:
```js
    rowEl.dataset.testid = 'ann-row';      // announcements.js
    rowEl.dataset.index = i;
```
```js
    rowEl.dataset.testid = 'staff-row';    // staff.js
    rowEl.dataset.index = i;
```
```js
    rowEl.dataset.testid = 'cal-event-row'; // calendar.js
    rowEl.dataset.index = i;
```
```js
    rowEl.dataset.testid = 'song-db-row';  // songs.js
    rowEl.dataset.index = i;
```
```js
    rowEl.dataset.testid = 'welcome-row';  // editor.js welcome render
    rowEl.dataset.index = i;
```
```js
    rowEl.dataset.testid = 'vr-row';       // editor.js volunteer-roles render
    rowEl.dataset.index = i;
```
Use the loop index variable already present at each site (`idx`, `i`, etc.).

- [ ] **Step 3: Confirm no behavior changed (unit tests still green)**

Run: `npm test`
Expected: existing vitest suite PASSES unchanged.

- [ ] **Step 4: Confirm the app still loads (manual quick check)**

Run: `APP_MODE=desktop python3 server.py` in one terminal, open `http://localhost:8765`, confirm the editor renders. Stop the server.
Expected: rows render normally; `data-testid` attributes present in DevTools.

- [ ] **Step 5: Commit**

```bash
git add src/js/editor.js src/js/announcements.js src/js/staff.js src/js/calendar.js src/js/songs.js
git commit -m "feat(test-seam): add data-testid/data-index to dynamic row renders"
```

---

### Task 7: Playwright config — two lanes, setup/teardown, webServer

**Files:**
- Create: `playwright.config.ts`

- [ ] **Step 1: Implement the config**

Create `playwright.config.ts`:
```ts
import { defineConfig, devices } from '@playwright/test';
import { config as loadDotenv } from 'dotenv';

loadDotenv({ path: '.env.e2e' });

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8080';

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: false,            // server.py is a shared single instance this phase
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'python3 server.py',
    url: `${BASE_URL}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      APP_MODE: 'server',
      DATABASE_URL: process.env.DATABASE_URL ?? '',
      SUPABASE_URL: process.env.SUPABASE_URL ?? '',
      SUPABASE_ANON_KEY: process.env.SUPABASE_ANON_KEY ?? '',
      SUPABASE_JWT_SECRET: process.env.SUPABASE_JWT_SECRET ?? '',
    },
  },
  projects: [
    { name: 'core-setup', testMatch: /helpers\/auth\.setup\.ts/, grep: /@core-setup/, teardown: 'core-teardown' },
    { name: 'core-teardown', testMatch: /helpers\/auth\.teardown\.ts/ },
    { name: 'live-setup', testMatch: /helpers\/auth\.setup\.ts/, grep: /@live-setup/ },
    {
      name: 'core',
      grep: /@core/,
      dependencies: ['core-setup'],
      use: { ...devices['Desktop Chrome'], storageState: 'tests/e2e/.auth/core.json' },
    },
    {
      name: 'live',
      grep: /@live/,
      dependencies: ['live-setup'],
      use: { ...devices['Desktop Chrome'], storageState: 'tests/e2e/.auth/live.json' },
    },
  ],
});
```

- [ ] **Step 2: Typecheck**

Run: `npx tsc -p tsconfig.e2e.json --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add playwright.config.ts
git commit -m "test(e2e): add two-lane Playwright config with webServer + setup/teardown"
```

---

### Task 8: Auth setup & teardown projects

> Setup signs in via supabase-js in a real browser context so we capture whatever localStorage key supabase-js uses, then save `storageState`. Core uses the ephemeral identity (ids written to disk for teardown); live uses `worship@`.

**Files:**
- Create: `tests/e2e/helpers/auth.setup.ts`
- Create: `tests/e2e/helpers/auth.teardown.ts`

- [ ] **Step 1: Implement `auth.setup.ts`**

Create `tests/e2e/helpers/auth.setup.ts`:
```ts
import { test as setup, expect } from '@playwright/test';
import { writeFileSync, mkdirSync } from 'node:fs';
import { e2eEnv } from './env';
import { createEphemeralIdentity } from './supabase-admin';

const CORE_STATE = 'tests/e2e/.auth/core.json';
const LIVE_STATE = 'tests/e2e/.auth/live.json';
const CORE_IDS = 'tests/e2e/.auth/core-ids.json';

/** Sign in through supabase-js in the page, then save storageState. */
async function signInAndSave(page: import('@playwright/test').Page, email: string, password: string, statePath: string) {
  await page.goto('/');
  // Wait for the app's supabase client + config to be available.
  await page.waitForFunction(() => !!(globalThis as any).BULLETIN_SUPABASE_CONFIG);
  const ok = await page.evaluate(async ({ email, password }) => {
    const cfg = (globalThis as any).BULLETIN_SUPABASE_CONFIG;
    const { createClient } = await import('https://esm.sh/@supabase/supabase-js@2');
    const sb = createClient(cfg.url, cfg.anonKey);
    const { error } = await sb.auth.signInWithPassword({ email, password });
    return !error;
  }, { email, password });
  if (!ok) throw new Error(`signInWithPassword failed for ${email}`);
  await page.reload();
  await expect.poll(async () =>
    (await page.request.get('/api/me')).status(),
  ).toBe(200);
  mkdirSync('tests/e2e/.auth', { recursive: true });
  await page.context().storageState({ path: statePath });
}

setup('@core-setup provision ephemeral identity', async ({ page }) => {
  const id = await createEphemeralIdentity('core');
  mkdirSync('tests/e2e/.auth', { recursive: true });
  writeFileSync(CORE_IDS, JSON.stringify(id));
  await signInAndSave(page, id.email, id.password, CORE_STATE);
});

setup('@live-setup sign in worship account', async ({ page }) => {
  const env = e2eEnv(['E2E_LIVE_EMAIL', 'E2E_LIVE_PASSWORD'] as const);
  await signInAndSave(page, env.E2E_LIVE_EMAIL, env.E2E_LIVE_PASSWORD, LIVE_STATE);
});
```

- [ ] **Step 2: Implement `auth.teardown.ts`**

Create `tests/e2e/helpers/auth.teardown.ts`:
```ts
import { test as teardown } from '@playwright/test';
import { readFileSync, existsSync, rmSync } from 'node:fs';
import { destroyEphemeralIdentity } from './supabase-admin';

const CORE_IDS = 'tests/e2e/.auth/core-ids.json';

teardown('destroy ephemeral identity', async () => {
  if (!existsSync(CORE_IDS)) return;
  const id = JSON.parse(readFileSync(CORE_IDS, 'utf8'));
  await destroyEphemeralIdentity(id);
  rmSync(CORE_IDS, { force: true });
});
```

- [ ] **Step 3: Typecheck**

Run: `npx tsc -p tsconfig.e2e.json --noEmit`
Expected: no errors.

- [ ] **Step 4: Smoke-run setup only (against test project)**

Run: `npx playwright test --project=core-setup`
Expected: PASS — creates `tests/e2e/.auth/core.json` and `core-ids.json`; teardown then deletes the identity. If the `esm.sh` import is blocked in CI, switch to bundling supabase-js via the app's own `/src/js/supabase-browser.js` (note for live-lane network policy).

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/helpers/auth.setup.ts tests/e2e/helpers/auth.teardown.ts
git commit -m "test(e2e): add auth setup/teardown for core + live lanes"
```

---

### Task 9: AppShell page object

**Files:**
- Create: `tests/e2e/pages/AppShell.ts`

- [ ] **Step 1: Implement the page object**

Create `tests/e2e/pages/AppShell.ts`:
```ts
import { type Page, type Locator, expect } from '@playwright/test';

const TABS = {
  editor: 'page-editor',
  files: 'page-files',
  songdb: 'page-songdb',
  format: 'page-format',
  templates: 'page-templates',
  settings: 'page-settings',
} as const;
export type TabName = keyof typeof TABS;

export class AppShell {
  constructor(private readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto('/');
    await expect(this.page.locator('.tab-bar')).toBeVisible();
  }

  tab(name: TabName): Locator {
    return this.page.locator(`[data-tab="${TABS[name]}"]`);
  }

  async switchTo(name: TabName): Promise<void> {
    await this.tab(name).click();
    await expect(this.tab(name)).toHaveAttribute('aria-selected', 'true');
  }

  /**
   * Assert the server-mode session is authenticated. Uses UI signals, NOT
   * page.request — page.request is a separate context that does not run the
   * app's JS, so it never attaches the supabase Bearer token that apiFetch adds.
   */
  async expectAuthenticated(): Promise<void> {
    await expect(this.page.locator('#login-screen')).toBeHidden();
    await expect(this.page.locator('#user-info')).toBeVisible();
  }
}
```

- [ ] **Step 2: Typecheck**

Run: `npx tsc -p tsconfig.e2e.json --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/pages/AppShell.ts
git commit -m "test(e2e): add AppShell page object"
```

---

### Task 10: The end-to-end smoke spec (both lanes green)

> Proves the whole harness: real server boot, authenticated session, tab nav, create+persist a project, export a valid PDF. The `@live` variant additionally asserts the real PCO connection is present (read-only).

**Files:**
- Create: `tests/e2e/flows/smoke.spec.ts`

- [ ] **Step 1: Write the smoke spec**

Create `tests/e2e/flows/smoke.spec.ts`:
```ts
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { AppShell } from '../pages/AppShell';
import { installClock, settlePersist } from '../helpers/clock';
import { assertValidPdf } from '../helpers/pdf';

test.describe('@core harness smoke', () => {
  test('boots, authenticates, navigates, persists a project, exports PDF', async ({ page }) => {
    await installClock(page);
    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();

    for (const tab of ['files', 'songdb', 'format', 'templates', 'settings', 'editor'] as const) {
      await shell.switchTo(tab);
    }

    // Create + persist a project via the UI.
    await shell.switchTo('editor');
    await page.locator('#bulletin-title').fill('E2E Smoke Bulletin');
    await page.locator('#svc-title').fill('Smoke Service');
    await page.locator('#add-item-btn').click();
    await page.locator('[data-testid="item-row"][data-index="0"] .item-title-input').fill('Welcome');
    await settlePersist(page);

    // Confirm it persisted by reloading and finding it in Files.
    await page.reload();
    await shell.switchTo('files');
    await expect(page.locator('#files-list')).toContainText('E2E Smoke Bulletin');

    // Export a PDF through the real UI button (authenticated, via app JS) and
    // assert the downloaded bytes are a valid PDF.
    await shell.switchTo('editor');
    const printBtn = page.locator('#btn-print');
    await expect(printBtn).toBeEnabled();
    const downloadPromise = page.waitForEvent('download');
    await printBtn.click();
    const download = await downloadPromise;
    const filePath = await download.path();
    expect(filePath).toBeTruthy();
    assertValidPdf(readFileSync(filePath!));
  });
});

test.describe('@live real-integration smoke', () => {
  test('worship account is authenticated and PCO is connected', async ({ page }) => {
    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();
    // PCO connected → the import view (hidden until connected) is visible.
    // Read-only: we never trigger an import here.
    await page.locator('#editor-toolbar-sync').click();
    await expect(page.locator('#pco-import-view')).toBeVisible();
  });
});
```

- [ ] **Step 2: Run the core smoke**

Run: `npm run test:e2e`
Expected: `core-setup` runs, then the `@core` smoke PASSES, then `core-teardown` deletes the identity.

- [ ] **Step 3: Run the live smoke**

Run: `npm run test:e2e:live`
Expected: `live-setup` signs in as `worship@`, then the `@live` smoke PASSES. (If the PCO token has lapsed, this is the expected loud signal — re-connect per runbook.)

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/flows/smoke.spec.ts
git commit -m "test(e2e): add two-lane end-to-end harness smoke"
```

---

### Task 11: CI — core gate workflow

**Files:**
- Create: `.github/workflows/e2e-core.yml`

- [ ] **Step 1: Implement the workflow**

Create `.github/workflows/e2e-core.yml`:
```yaml
name: E2E Core (PR gate)
on:
  push:
    branches: [main]
  pull_request:
jobs:
  e2e-core:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm' }
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - name: Run core lane
        env:
          CI: 'true'
          SUPABASE_URL: ${{ secrets.E2E_SUPABASE_URL }}
          SUPABASE_ANON_KEY: ${{ secrets.E2E_SUPABASE_ANON_KEY }}
          SUPABASE_JWT_SECRET: ${{ secrets.E2E_SUPABASE_JWT_SECRET }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.E2E_SUPABASE_SERVICE_ROLE_KEY }}
          DATABASE_URL: ${{ secrets.E2E_DATABASE_URL }}
        run: npx playwright test --project=core
      - uses: actions/upload-artifact@v4
        if: failure()
        with: { name: playwright-report, path: playwright-report/, retention-days: 7 }
```

- [ ] **Step 2: Validate YAML locally**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/e2e-core.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/e2e-core.yml
git commit -m "ci(e2e): add core lane PR gate workflow"
```

---

### Task 12: CI — live lane workflow

**Files:**
- Create: `.github/workflows/e2e-live.yml`

- [ ] **Step 1: Implement the workflow**

Create `.github/workflows/e2e-live.yml`:
```yaml
name: E2E Live (real integrations)
on:
  schedule:
    - cron: '0 9 * * *'   # nightly 09:00 UTC
  workflow_dispatch:
jobs:
  e2e-live:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm' }
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - name: Run live lane
        env:
          CI: 'true'
          SUPABASE_URL: ${{ secrets.E2E_SUPABASE_URL }}
          SUPABASE_ANON_KEY: ${{ secrets.E2E_SUPABASE_ANON_KEY }}
          SUPABASE_JWT_SECRET: ${{ secrets.E2E_SUPABASE_JWT_SECRET }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.E2E_SUPABASE_SERVICE_ROLE_KEY }}
          DATABASE_URL: ${{ secrets.E2E_DATABASE_URL }}
          E2E_LIVE_EMAIL: ${{ secrets.E2E_LIVE_EMAIL }}
          E2E_LIVE_PASSWORD: ${{ secrets.E2E_LIVE_PASSWORD }}
        run: npx playwright test --project=live
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: playwright-report-live, path: playwright-report/, retention-days: 14 }
```

- [ ] **Step 2: Validate YAML locally**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/e2e-live.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/e2e-live.yml
git commit -m "ci(e2e): add live lane scheduled workflow"
```

---

## Phase 1 exit criteria

- `npm run test:e2e` is green locally: ephemeral identity provisioned → smoke passes → identity destroyed.
- `npm run test:e2e:live` is green locally against `worship@`.
- `npm test` (vitest) still green — no app behavior changed.
- Both CI workflows present and YAML-valid; core gate runs on PRs.
- Secrets documented in `.env.e2e.example`; real values added to GitHub Secrets (`E2E_*`).

---

## Roadmap — subsequent phases (each becomes its own plan)

These are intentionally NOT expanded here; each will be authored as a standalone plan once Phase 1 lands and the patterns/schema unknowns are resolved.

- **Phase 2 — Page Object layer.** One typed page object per area: `EditorPage`, `ProjectsPage`, `PcoPanel`, `CalendarPanel`, `SongDbPage`, `FormatPage`, `TemplatesPage`, `SettingsPage`, `AnnouncementsPanel`, `StaffPanel`, `VolunteerRolesPanel`, `PreviewPane`, `AuthFlow`. Each exposes accessors keyed off the `data-testid` convention from Task 6.
- **Phase 3 — Golden-path flows** (spec §6 flows): PCO import→edit→autosave→save-version→export; build-from-scratch; bulk export; calendar render; conflict resolution. Core lane uses recorded PCO/Google HARs; introduce `tests/e2e/helpers/record-replay.ts` (`routeFromHAR`) here, recorded by the live lane.
- **Phase 4 — Exhaustive per-feature specs** filling every coverage-matrix row (spec §6). One spec file per area; a checklist tracks matrix completion.
- **Phase 5 — Fixture auto-refresh + hardening.** Live lane re-records HARs and opens a PR on diff; flake-quarantine policy; optional thin Electron boot-smoke (deferred from v1 per spec §9).
