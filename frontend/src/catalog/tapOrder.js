function entryTime(value) {
  if (typeof value !== "string" || !value) return null;
  // FastAPI's existing naive UTC DateTime serialization has no timezone suffix.
  const utc = /(?:Z|[+-]\d\d:\d\d)$/i.test(value) ? value : `${value}Z`;
  const time = Date.parse(utc);
  return Number.isFinite(time) ? time : null;
}

export function compareTapBeers(a, b) {
  if (Boolean(a.is_featured) !== Boolean(b.is_featured)) return a.is_featured ? -1 : 1;
  if (!a.is_featured) {
    const first = entryTime(a.tap_entered_at);
    const second = entryTime(b.tap_entered_at);
    if (first !== second) {
      if (first === null) return 1;
      if (second === null) return -1;
      return second - first;
    }
  }
  return ((a.tap_position || 999) - (b.tap_position || 999)) || (Number(a.id) - Number(b.id));
}
