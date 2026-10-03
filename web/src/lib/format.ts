/** The exhibit's language, for dates and country names. */
export const LOCALE = 'en-GB';

// Timestamps are shown in UTC, and say so: the same instant on server and browser, never the
// viewer's local time silently.
const TIME_ZONE = 'UTC';

const utcTimestamp = new Intl.DateTimeFormat(LOCALE, {
	dateStyle: 'medium',
	timeStyle: 'medium',
	timeZone: TIME_ZONE
});

/** "25 Sept 2026, 14:02:01 UTC" from an ISO 8601 timestamp. */
export function formatUtc(iso: string): string {
	return `${utcTimestamp.format(new Date(iso))} UTC`;
}

const utcDay = new Intl.DateTimeFormat(LOCALE, {
	weekday: 'short',
	day: 'numeric',
	month: 'short',
	timeZone: TIME_ZONE
});

/** "Sat 3 Oct" from an ISO 8601 date: a UTC day. */
export function formatUtcDay(isoDate: string): string {
	return utcDay.format(new Date(isoDate));
}

/** A request's target as sent: its path, and its query after a `?` when there was one. */
export function requestTarget({ path, query }: { path: string; query: string | null }): string {
	return query === null ? path : `${path}?${query}`;
}

const counts = new Intl.NumberFormat(LOCALE);

/** "1,032,774". */
export function formatCount(count: number): string {
	return counts.format(count);
}

const MS_PER_HOUR = 3_600_000;
const HOURS_PER_DAY = 24;
// Up to two days, a span reads better in hours.
const MAX_HOURS_SHOWN = 48;

/** How long from `from` to `to`: "35 hours", "12 days". */
export function formatSpan(from: string, to: string): string {
	const hours = Math.round((Date.parse(to) - Date.parse(from)) / MS_PER_HOUR);
	if (hours < MAX_HOURS_SHOWN) {
		return hours === 1 ? '1 hour' : `${String(hours)} hours`;
	}
	return `${String(Math.round(hours / HOURS_PER_DAY))} days`;
}

const MS_PER_SECOND = 1000;
const SECONDS_PER_MINUTE = 60;
// Up to two minutes, a gap reads better in seconds; up to two hours, in minutes.
const MAX_SECONDS_SHOWN = 120;
const MAX_MINUTES_SHOWN = 120;

/** How long from `from` to `to`, for steps close together: "4 s", "12 min", then formatSpan's. */
export function formatGap(from: string, to: string): string {
	const seconds = Math.round((Date.parse(to) - Date.parse(from)) / MS_PER_SECOND);
	if (seconds < MAX_SECONDS_SHOWN) {
		return `${String(seconds)} s`;
	}
	const minutes = Math.round(seconds / SECONDS_PER_MINUTE);
	if (minutes < MAX_MINUTES_SHOWN) {
		return `${String(minutes)} min`;
	}
	return formatSpan(from, to);
}
