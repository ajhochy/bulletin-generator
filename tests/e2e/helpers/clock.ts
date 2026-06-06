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
