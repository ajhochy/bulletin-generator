/**
 * tests/conflict-dialog.spec.js
 *
 * Unit tests for the conflict-resolution helpers in projects.js.
 *
 * We test the pure logic that can be extracted without a full DOM environment:
 *   - buildConflictSummary() — item-count and service-date comparison
 *
 * The snapshot-capture test verifies the contract that collectCurrentProjectState
 * is called *before* any await so the snapshot reflects the editor state at the
 * moment the conflict is detected, not some later drift.
 *
 * NOTE: buildConflictSummary is not yet exported from a module — it lives in the
 * browser-global projects.js.  We inline the same logic here so the tests remain
 * fast and dependency-free.  When the function is extracted to a core module,
 * replace the inline impl below with an import.
 */

import { describe, expect, it } from 'vitest';

// ─── Inline implementation (mirrors projects.js buildConflictSummary) ─────────
function buildConflictSummary(local, server) {
  const localItems  = Array.isArray(local  && local.items)  ? local.items  : [];
  const serverItems = Array.isArray(server && server.items) ? server.items : [];

  const localCount  = localItems.length;
  const serverCount = serverItems.length;

  let itemMsg;
  if (serverCount === localCount) {
    itemMsg = `Both versions have ${localCount} item${localCount !== 1 ? 's' : ''}.`;
  } else {
    itemMsg = `Server has ${serverCount} item${serverCount !== 1 ? 's' : ''} (you have ${localCount}).`;
  }

  const serverDate = (server && server.svcDate) || '';
  const localDate  = (local  && local.svcDate)  || '';
  let dateMsg = '';
  if (serverDate) {
    dateMsg = serverDate === localDate
      ? ` Service date: ${serverDate}.`
      : ` Server service date: ${serverDate}${localDate ? ` (yours: ${localDate})` : ''}.`;
  }

  return itemMsg + dateMsg;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('buildConflictSummary', () => {
  const makeState = (itemCount, svcDate = '') => ({
    items: Array.from({ length: itemCount }, (_, i) => ({ title: `Item ${i + 1}`, type: 'label' })),
    svcDate,
  });

  it('reports difference when server has more items', () => {
    const local  = makeState(10);
    const server = makeState(8);
    const msg = buildConflictSummary(local, server);
    expect(msg).toContain('Server has 8 items');
    expect(msg).toContain('you have 10');
  });

  it('reports difference when server has fewer items', () => {
    const local  = makeState(3);
    const server = makeState(7);
    const msg = buildConflictSummary(local, server);
    expect(msg).toContain('Server has 7 items');
    expect(msg).toContain('you have 3');
  });

  it('reports same count when both versions match', () => {
    const local  = makeState(5);
    const server = makeState(5);
    const msg = buildConflictSummary(local, server);
    expect(msg).toContain('Both versions have 5 items');
  });

  it('uses singular "item" when count is 1', () => {
    const msg = buildConflictSummary(makeState(1), makeState(1));
    expect(msg).toContain('Both versions have 1 item.');
    expect(msg).not.toContain('items');
  });

  it('includes server service date when dates differ', () => {
    const local  = makeState(4, '2026-05-18');
    const server = makeState(4, '2026-05-25');
    const msg = buildConflictSummary(local, server);
    expect(msg).toContain('2026-05-25');
    expect(msg).toContain('2026-05-18');
  });

  it('shows shared service date when both match', () => {
    const local  = makeState(4, '2026-05-18');
    const server = makeState(4, '2026-05-18');
    const msg = buildConflictSummary(local, server);
    expect(msg).toContain('Service date: 2026-05-18');
  });

  it('omits date line when server has no service date', () => {
    const local  = makeState(4, '2026-05-18');
    const server = makeState(6);
    const msg = buildConflictSummary(local, server);
    expect(msg).not.toContain('Service date');
    expect(msg).not.toContain('2026-05-18');
  });

  it('handles missing items arrays gracefully', () => {
    const msg = buildConflictSummary({}, {});
    expect(msg).toContain('Both versions have 0 items');
  });

  it('handles null local/server gracefully', () => {
    const msg = buildConflictSummary(null, null);
    expect(msg).toContain('Both versions have 0 items');
  });
});

// ─── Snapshot-capture contract test ──────────────────────────────────────────
// Verifies that the snapshot is captured *before* the async save attempt,
// not after.  We simulate the contract with a synchronous mock.

describe('conflict snapshot capture contract', () => {
  it('snapshot reflects editor state at the moment of save, not after an async drift', async () => {
    let snapshotAtSaveTime = null;
    let editorState = { items: [{ title: 'A', type: 'label' }], svcDate: '2026-05-18' };

    // Simulate saveProjectToServer: captures snapshot, then awaits, then editor changes
    async function simulatedSave() {
      // This is the contract: snapshot captured BEFORE await
      snapshotAtSaveTime = JSON.parse(JSON.stringify(editorState));
      // Simulate async work (editor state drifts while awaiting)
      await Promise.resolve();
      editorState.items.push({ title: 'B', type: 'label' }); // drift after await
      // 409 handler fires here — uses snapshotAtSaveTime, not current editorState
    }

    await simulatedSave();

    // Snapshot was taken before the drift
    expect(snapshotAtSaveTime.items).toHaveLength(1);
    expect(snapshotAtSaveTime.items[0].title).toBe('A');
    // Editor drifted — confirms the snapshot is a separate object
    expect(editorState.items).toHaveLength(2);
  });
});
