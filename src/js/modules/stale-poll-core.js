/**
 * stale-poll-core.js — pure helpers for stale project detection.
 *
 * These functions contain no DOM or global state references so they can be
 * unit-tested in Node/vitest without a browser environment.
 */

/**
 * Format a relative time string from an ISO timestamp.
 *
 * @param {string|null} isoString  ISO 8601 timestamp string
 * @param {number} [nowMs]         Override for Date.now() — useful in tests
 * @returns {string}  e.g. "just now", "3m ago", "2h ago", "5d ago", ""
 */
export function formatStaleRelativeTime(isoString, nowMs = Date.now()) {
  if (!isoString) return '';
  const then = new Date(isoString);
  if (isNaN(then.getTime())) return '';
  const diffMs = nowMs - then.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return 'just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

/**
 * Build the "who updated" portion of the stale banner message.
 *
 * @param {string|null} updatedByEmail
 * @param {string|null} updatedByName
 * @param {string|null} updatedAt     ISO 8601 timestamp
 * @param {number} [nowMs]            Override for Date.now() — useful in tests
 * @returns {string}  e.g. "Updated by alice@example.com · 3m ago"
 */
export function buildStaleBannerMessage(updatedByEmail, updatedByName, updatedAt, nowMs = Date.now()) {
  const who = updatedByEmail || updatedByName || 'Someone';
  const when = formatStaleRelativeTime(updatedAt, nowMs);
  let msg = `Updated by ${who}`;
  if (when) msg += ` · ${when}`;
  return msg;
}
