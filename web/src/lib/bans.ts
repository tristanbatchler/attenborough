// How long a ban made in the admin area lasts: the choices its form offers. Durations rather than
// a date, so there is no time zone to get wrong.

/** The ban form's fields, read by the page's actions. */
export const DURATION_FIELD = 'duration';
export const REASON_FIELD = 'reason';
export const BAN_ID_FIELD = 'ban_id';

const MS_PER_HOUR = 3_600_000;

export const BAN_DURATIONS = [
	{ value: '1h', label: '1 hour', hours: 1 },
	{ value: '1d', label: '1 day', hours: 24 },
	{ value: '7d', label: '1 week', hours: 168 },
	{ value: '30d', label: '30 days', hours: 720 },
	{ value: 'forever', label: 'Until revoked', hours: null }
] as const;

export type BanDuration = (typeof BAN_DURATIONS)[number];

/** When a ban of `duration` made now ends, as ISO 8601; null for one that doesn't. */
export function banExpiry(duration: BanDuration): string | null {
	return duration.hours === null
		? null
		: new Date(Date.now() + duration.hours * MS_PER_HOUR).toISOString();
}
