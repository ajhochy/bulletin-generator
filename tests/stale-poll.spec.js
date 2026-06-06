/**
 * tests/stale-poll.spec.js — unit tests for stale poll helper functions.
 *
 * Covers:
 *   formatStaleRelativeTime:
 *     - "just now" for timestamps < 60 seconds ago
 *     - "Xm ago" for timestamps in the minutes range
 *     - "Xh ago" for timestamps in the hours range
 *     - "Xd ago" for timestamps in the days range
 *     - "" for null/undefined/invalid inputs
 *
 *   buildStaleBannerMessage:
 *     - Includes updated_by_email when available
 *     - Falls back to updated_by_name when email is absent
 *     - Falls back to "Someone" when neither email nor name is provided
 *     - Includes relative time in the message
 *     - Omits time suffix when timestamp is absent
 */

import { describe, expect, it } from 'vitest';
import {
  formatStaleRelativeTime,
  buildStaleBannerMessage,
} from '../src/js/modules/stale-poll-core.js';

// ── formatStaleRelativeTime ───────────────────────────────────────────────────

describe('formatStaleRelativeTime', () => {
  const makeNow = (offsetMs = 0) => {
    const base = new Date('2026-05-20T12:00:00Z').getTime();
    return base + offsetMs;
  };

  it('returns "just now" for a timestamp 0 seconds ago', () => {
    const nowMs = makeNow();
    const iso = new Date(nowMs).toISOString();
    expect(formatStaleRelativeTime(iso, nowMs)).toBe('just now');
  });

  it('returns "just now" for a timestamp 59 seconds ago', () => {
    const nowMs = makeNow();
    const iso = new Date(nowMs - 59_000).toISOString();
    expect(formatStaleRelativeTime(iso, nowMs)).toBe('just now');
  });

  it('returns "1m ago" for a timestamp exactly 60 seconds ago', () => {
    const nowMs = makeNow();
    const iso = new Date(nowMs - 60_000).toISOString();
    expect(formatStaleRelativeTime(iso, nowMs)).toBe('1m ago');
  });

  it('returns "3m ago" for a timestamp 3 minutes ago', () => {
    const nowMs = makeNow();
    const iso = new Date(nowMs - 3 * 60_000).toISOString();
    expect(formatStaleRelativeTime(iso, nowMs)).toBe('3m ago');
  });

  it('returns "59m ago" for a timestamp 59 minutes ago', () => {
    const nowMs = makeNow();
    const iso = new Date(nowMs - 59 * 60_000).toISOString();
    expect(formatStaleRelativeTime(iso, nowMs)).toBe('59m ago');
  });

  it('returns "1h ago" for a timestamp exactly 60 minutes ago', () => {
    const nowMs = makeNow();
    const iso = new Date(nowMs - 60 * 60_000).toISOString();
    expect(formatStaleRelativeTime(iso, nowMs)).toBe('1h ago');
  });

  it('returns "2h ago" for a timestamp 2 hours ago', () => {
    const nowMs = makeNow();
    const iso = new Date(nowMs - 2 * 3_600_000).toISOString();
    expect(formatStaleRelativeTime(iso, nowMs)).toBe('2h ago');
  });

  it('returns "1d ago" for a timestamp exactly 24 hours ago', () => {
    const nowMs = makeNow();
    const iso = new Date(nowMs - 24 * 3_600_000).toISOString();
    expect(formatStaleRelativeTime(iso, nowMs)).toBe('1d ago');
  });

  it('returns "5d ago" for a timestamp 5 days ago', () => {
    const nowMs = makeNow();
    const iso = new Date(nowMs - 5 * 86_400_000).toISOString();
    expect(formatStaleRelativeTime(iso, nowMs)).toBe('5d ago');
  });

  it('returns "" for null input', () => {
    expect(formatStaleRelativeTime(null)).toBe('');
  });

  it('returns "" for undefined input', () => {
    expect(formatStaleRelativeTime(undefined)).toBe('');
  });

  it('returns "" for an empty string', () => {
    expect(formatStaleRelativeTime('')).toBe('');
  });

  it('returns "" for a non-date string', () => {
    expect(formatStaleRelativeTime('not-a-date')).toBe('');
  });
});

// ── buildStaleBannerMessage ───────────────────────────────────────────────────

describe('buildStaleBannerMessage', () => {
  const nowMs = new Date('2026-05-20T12:00:00Z').getTime();
  const threeMinutesAgo = new Date(nowMs - 3 * 60_000).toISOString();

  it('includes updated_by_email when available', () => {
    const msg = buildStaleBannerMessage('alice@example.com', 'Alice', threeMinutesAgo, nowMs);
    expect(msg).toContain('alice@example.com');
  });

  it('does not include name when email is present', () => {
    const msg = buildStaleBannerMessage('alice@example.com', 'Alice', threeMinutesAgo, nowMs);
    // Email takes priority; name should not appear separately
    expect(msg).not.toContain('Alice');
  });

  it('falls back to updated_by_name when email is absent', () => {
    const msg = buildStaleBannerMessage(null, 'Alice', threeMinutesAgo, nowMs);
    expect(msg).toContain('Alice');
  });

  it('falls back to "Someone" when neither email nor name is provided', () => {
    const msg = buildStaleBannerMessage(null, null, threeMinutesAgo, nowMs);
    expect(msg).toContain('Someone');
  });

  it('falls back to "Someone" for empty string email and name', () => {
    const msg = buildStaleBannerMessage('', '', threeMinutesAgo, nowMs);
    expect(msg).toContain('Someone');
  });

  it('includes relative time in the message', () => {
    const msg = buildStaleBannerMessage('alice@example.com', null, threeMinutesAgo, nowMs);
    expect(msg).toContain('3m ago');
  });

  it('starts with "Updated by"', () => {
    const msg = buildStaleBannerMessage('alice@example.com', null, threeMinutesAgo, nowMs);
    expect(msg.startsWith('Updated by')).toBe(true);
  });

  it('omits time portion when updated_at is null', () => {
    const msg = buildStaleBannerMessage('alice@example.com', null, null, nowMs);
    expect(msg).toBe('Updated by alice@example.com');
    expect(msg).not.toContain('·');
  });

  it('separates identity and time with " · "', () => {
    const msg = buildStaleBannerMessage('alice@example.com', null, threeMinutesAgo, nowMs);
    expect(msg).toContain(' · ');
  });
});
