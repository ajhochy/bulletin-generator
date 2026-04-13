export function shouldRefreshCalendar({ force, calEvents, calLastFetch, now, cacheMs }) {
  if (force) return true;
  if (calEvents === null || calEvents === false) return true;
  return (now - calLastFetch) >= cacheMs;
}

export function mergeCalendarEvents(oldEvents, freshEvents) {
  const previous = Array.isArray(oldEvents) ? oldEvents : [];
  return (Array.isArray(freshEvents) ? freshEvents : []).map(freshEv => {
    const match = previous.find(old =>
      old.start.iso === freshEv.start.iso &&
      (old._srcTitle || old.title).toLowerCase() === freshEv.title.toLowerCase()
    );
    if (match) {
      return { ...freshEv, title: match.title, location: match.location, _srcTitle: freshEv.title };
    }
    return { ...freshEv, _srcTitle: freshEv.title };
  });
}

export function deriveCalendarFetchState({ data, previousEvents, fetchedAt }) {
  if (data && data.ok) {
    const events = mergeCalendarEvents(previousEvents, data.events);
    const count = events.length;
    return {
      calEvents: events,
      calLastFetch: fetchedAt,
      statusText: `${count} event${count === 1 ? '' : 's'} loaded`,
      statusIsError: false,
    };
  }

  return {
    calEvents: false,
    calLastFetch: 0,
    statusText: 'Calendar unavailable',
    statusIsError: true,
  };
}

export function deriveCalendarFetchErrorState(error) {
  const msg = error && error.message ? error.message : String(error);
  return {
    calEvents: false,
    calLastFetch: 0,
    statusText: `Fetch failed: ${msg}`,
    statusIsError: true,
  };
}
