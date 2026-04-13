import { describe, expect, it } from 'vitest';
import {
  deriveCalendarFetchErrorState,
  deriveCalendarFetchState,
  mergeCalendarEvents,
  shouldRefreshCalendar,
} from '../src/js/modules/calendar-core.js';

describe('calendar core', () => {
  it('respects cache freshness unless forced', () => {
    expect(shouldRefreshCalendar({
      force: false,
      calEvents: [{ title: 'A' }],
      calLastFetch: 1_000,
      now: 2_000,
      cacheMs: 5_000,
    })).toBe(false);

    expect(shouldRefreshCalendar({
      force: true,
      calEvents: [{ title: 'A' }],
      calLastFetch: 1_000,
      now: 2_000,
      cacheMs: 5_000,
    })).toBe(true);
  });

  it('merges fresh events while preserving user edits', () => {
    const merged = mergeCalendarEvents(
      [{ title: 'Edited title', _srcTitle: 'Original', start: { iso: '2026-04-11T09:00:00' }, location: 'Hall' }],
      [{ title: 'Original', start: { iso: '2026-04-11T09:00:00' }, location: 'Room 1' }]
    );

    expect(merged).toEqual([
      {
        title: 'Edited title',
        _srcTitle: 'Original',
        start: { iso: '2026-04-11T09:00:00' },
        location: 'Hall',
      },
    ]);
  });

  it('derives success state from fetch data', () => {
    const next = deriveCalendarFetchState({
      data: { ok: true, events: [{ title: 'Original', start: { iso: '2026-04-11T09:00:00' }, location: 'Room 1' }] },
      previousEvents: [{ title: 'Edited', _srcTitle: 'Original', start: { iso: '2026-04-11T09:00:00' }, location: 'Hall' }],
      fetchedAt: 1234,
    });

    expect(next).toEqual({
      calEvents: [{ title: 'Edited', _srcTitle: 'Original', start: { iso: '2026-04-11T09:00:00' }, location: 'Hall' }],
      calLastFetch: 1234,
      statusText: '1 event loaded',
      statusIsError: false,
    });
  });

  it('derives unavailable and error states', () => {
    expect(deriveCalendarFetchState({
      data: { ok: false },
      previousEvents: [],
      fetchedAt: 1234,
    })).toEqual({
      calEvents: false,
      calLastFetch: 0,
      statusText: 'Calendar unavailable',
      statusIsError: true,
    });

    expect(deriveCalendarFetchErrorState(new Error('boom'))).toEqual({
      calEvents: false,
      calLastFetch: 0,
      statusText: 'Fetch failed: boom',
      statusIsError: true,
    });
  });
});
