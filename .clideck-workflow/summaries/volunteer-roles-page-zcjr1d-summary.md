# Volunteer Roles Page

Add a new persistent "Volunteer Roles" bulletin section that lives between Calendar and Volunteering Today — stored server-side in its own JSON file, editable via a card-based sidebar panel, and rendered in the live preview using the same bottom-zone pattern as the Announcements and Serving sections.

---

## Issues & Commits

| # | Title | Commit(s) |
|---|-------|-----------|
| [#231](https://github.com/ajhochy/bulletin-generator/issues/231) | Create data/volunteer-roles.example.json seed file | f8194b5 |
| [#232](https://github.com/ajhochy/bulletin-generator/issues/232) | Add VOLUNTEER_ROLES_FILE constants in server.py | 75242f6 |
| [#233](https://github.com/ajhochy/bulletin-generator/issues/233) | Initialize volunteer-roles.json at startup in server.py | d358d5d |
| [#234](https://github.com/ajhochy/bulletin-generator/issues/234) | Register /api/volunteer-roles GET and POST routes in server.py | f3909ca |
| [#235](https://github.com/ajhochy/bulletin-generator/issues/235) | Add _handle_get_volunteer_roles and _handle_post_volunteer_roles | a4b7914 |
| [#236](https://github.com/ajhochy/bulletin-generator/issues/236) | Add 'volunteer_roles' to zone-binding validation whitelist | 18112ed |
| [#237](https://github.com/ajhochy/bulletin-generator/issues/237) | Insert z-volunteer-roles zone in Classic template and renumber | 8952831 |
| [#238](https://github.com/ajhochy/bulletin-generator/issues/238) | Insert z-volunteer-roles zone in Modern template and renumber | 4e5f2f3 |
| [#239](https://github.com/ajhochy/bulletin-generator/issues/239) | Add migration M006_insert_volunteer_roles_zone in server.py | 938ebfc |
| [#240](https://github.com/ajhochy/bulletin-generator/issues/240) | Add 'volunteer_roles' to DEFAULT_PREVIEW_ZONE_ORDER | e9a17b1, 097a69d |
| [#241](https://github.com/ajhochy/bulletin-generator/issues/241) | Extend state.js with vrData global, setter, bottomMerge key, DOM ref | ec9190f |
| [#242](https://github.com/ajhochy/bulletin-generator/issues/242) | Create src/js/volunteer-roles.js mirroring announcements.js | 1fafc59 |
| [#243](https://github.com/ajhochy/bulletin-generator/issues/243) | Register volunteer-roles.js in LEGACY_SCRIPT_PATHS in main.js | 12d7b09 |
| [#244](https://github.com/ajhochy/bulletin-generator/issues/244) | Add #panel-section-volunteer-roles to index.html | 60dd317 |
| [#245](https://github.com/ajhochy/bulletin-generator/issues/245) | Load /api/volunteer-roles in loadAllFromServer (api.js) | 051c39e |
| [#246](https://github.com/ajhochy/bulletin-generator/issues/246) | Wire vrAddBtn click handler in editor.js init | 54d0fc6 |
| [#247](https://github.com/ajhochy/bulletin-generator/issues/247) | Add renderVolunteerRolesZone() to preview.js | 269166e |
| [#248](https://github.com/ajhochy/bulletin-generator/issues/248) | Trigger preview refresh when volunteer roles change | dc93f23 |

---

## Manual Setup Needed

None. This is a purely software feature — no API keys, environment variables, webhooks, or external service configuration required. The new `data/volunteer-roles.json` file is auto-initialized at server startup from the `data/volunteer-roles.example.json` seed, and the M006 migration updates existing templates on next restart.
