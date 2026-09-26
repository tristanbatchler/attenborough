// Timestamps are shown in UTC, and say so: the same instant on server and browser, never the
// viewer's local time silently.
const utcTimestamp = new Intl.DateTimeFormat('en-GB', {
	dateStyle: 'medium',
	timeStyle: 'medium',
	timeZone: 'UTC'
});

/** "25 Sept 2026, 14:02:01 UTC" from an ISO 8601 timestamp. */
export function formatUtc(iso: string): string {
	return `${utcTimestamp.format(new Date(iso))} UTC`;
}
