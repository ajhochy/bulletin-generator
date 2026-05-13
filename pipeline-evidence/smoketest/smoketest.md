# Smoke Test

Scope: `Volunteer-Roles-Page` (`main...dc93f23`) for the planned Volunteer Roles persistent bulletin section.
Date: 2026-05-12

## Findings

- Acceptance baseline is `state.plan`: add a global, persistent Volunteer Roles section between Calendar and Volunteering Today/serving in editor navigation and preview rendering.
- Planned backend behavior: seed `data/volunteer-roles.example.json`, initialize `data/volunteer-roles.json`, expose `/api/volunteer-roles` GET/POST with array validation, permit `volunteer_roles` template bindings, and migrate existing templates idempotently.
- Planned frontend behavior: hydrate global `vrData`, render card-based editor UI with add/remove/reorder/title/body/url fields, save changes to `/api/volunteer-roles`, refresh preview, and render the bottom-zone section through `appendBottomSection(contentEl, 'volunteerRoles')`.
- Coherence rules require `volunteer_roles` snake_case for bindings, `volunteerRoles` camelCase only for bottom merge, zone order calendar=7, volunteer_roles=8, serving_schedule=9, staff=10, global state only, no project-state persistence, and no static `volunteer-roles.js` script tag.
- Diff evidence touches the planned files plus `tests/preview-core.spec.js` and pipeline evidence files; no `src/js/projects.js` changes are present in the diff.
- The requested local smoke-test skill path `/Users/ajhochhalter/.clideck/skills/smoke-test/SKILL.md` was missing, so this checklist follows the requested compact format and workflow-specific acceptance baseline.

## Checks

| Area | Check | How to run | Result | Reasoning |
| --- | --- | --- | --- | --- |
| Setup | Volunteer Roles seed file exists and is exactly a valid empty JSON array. | `python3 -c "import json, pathlib; p=pathlib.Path('data/volunteer-roles.example.json'); data=json.load(p.open()); assert data == [], data"` | Success | `data/volunteer-roles.example.json` parsed as `[]`. |
| Backend | Server implementation compiles and includes constants, startup initialization, GET/POST route dispatch, handlers, and array validation for `/api/volunteer-roles`. | `python3 -m py_compile server.py` plus targeted Python source assertions. | Success | `server.py` compiles; 9 targeted assertions passed for constants, initialization, routes, handlers, validation, and binding whitelist. |
| Backend | Live `/api/volunteer-roles` endpoint initializes missing data, accepts array POST, persists it, and rejects non-array POST with HTTP 400. | Start `python3 server.py 8097`; use `curl` GET/POST checks against `http://127.0.0.1:8097/api/volunteer-roles`. | Success | Server initialized `volunteer-roles.json`; GET returned `[]`, array POST returned `{"ok": true}`, follow-up GET returned `Greeter`, and non-array POST returned HTTP 400 with `body must be an array`. |
| Templates | Built-in Classic and Modern templates include `volunteer_roles` between calendar and serving/staff with required orders 7/8/9/10. | Python import/source assertions over `server._classic_template()` and `server._modern_template()`. | Success | Classic and Modern both expose calendar=7, volunteer_roles=8, serving_schedule=9, staff=10; volunteer zone is enabled with title/body/url elements. |
| Migration | `M006_insert_volunteer_roles_zone` is registered and idempotently inserts exactly one volunteer_roles zone while bumping existing orders >= 8. | Python script with a temporary `TEMPLATES_FILE`, `MIGRATIONS_FILE`, `_migration_006_insert_volunteer_roles_zone()` called twice. | Success | Registry includes M006; two direct runs against a temp template produced exactly one volunteer_roles zone and orders calendar=7, volunteer_roles=8, serving_schedule=9, staff=10. |
| Frontend | Default preview order includes `volunteer_roles` between `calendar` and `serving_schedule`, and existing preview-core tests pass. | `npm test -- tests/preview-core.spec.js`. | Success | Vitest passed `tests/preview-core.spec.js`: 8 tests passed, including fallback order with `volunteer_roles` between `calendar` and `serving_schedule`. |
| Frontend | Editor sidebar has `panel-section-volunteer-roles` between Calendar and Volunteers and exposes `vr-list`/`vr-add-btn`. | Python text-order assertions against `index.html`. | Success | `index.html` order is Calendar panel < Volunteer Roles panel < Volunteers panel; `vr-list` and `vr-add-btn` are present; no static volunteer-roles script tag was added. |
| Frontend | Global state, legacy script loading, API hydration, and editor init wiring are coherent: `vrData`, `setVrData`, `volunteerRoles`, `vr-add-btn`, dynamic legacy script, normalized API load, add button handler, and initial render. | Targeted source assertions across `src/js/state.js`, `src/js/main.js`, `src/js/api.js`, and `src/js/editor.js`. | Success | Assertions passed for `vrData`, `setVrData`, `bottomMerge.volunteerRoles`, `vr-add-btn`, dynamic legacy script path after announcements, `/api/volunteer-roles` hydration with normalized fields, add handler, and initial `vrRender()`. |
| Frontend | `src/js/volunteer-roles.js` is a classic script, parses, renders cards with required fields/buttons/toolbar, saves to `/api/volunteer-roles`, and schedules preview updates for add/delete/move/edit. | `node --check src/js/volunteer-roles.js` plus targeted source assertions. | Success | `node --check` passed; assertions confirmed no imports/exports, required render/save/mutation/format functions, card classes/inputs/toolbar, POST endpoint, add schema, and 6 preview update calls. |
| Frontend | Preview renderer registers `volunteer_roles`, renders from `vrData`, uses bottom-zone merge key `volunteerRoles`, exposes rendered role title/body/url, and no project-state persistence was added. | Targeted source assertions over `src/js/preview.js`, `src/js/projects.js`, and diff vs `main`. | Success | Renderer is registered as `volunteer_roles`, guards on `vrData`, renders heading/title/body/QR URL, calls `appendBottomSection(contentEl, 'volunteerRoles')`, sets `lastRenderedBinding`, and `projects.js` is unchanged with no volunteer-role persistence. |

## Known Gaps

- Browser UI interaction was not selected as a required check because the planned behavior is demonstrable through live HTTP checks and targeted source/test assertions; no cross-app behavior is involved.
