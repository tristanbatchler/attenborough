// How the blog writes dates: WordPress's default "F j, Y" (August 19, 2026) and RFC 2822 in feeds.

const display = new Intl.DateTimeFormat('en-US', {
	year: 'numeric',
	month: 'long',
	day: 'numeric',
	timeZone: 'UTC'
});

export function displayDate(iso: string): string {
	return display.format(new Date(iso));
}

/** "Wed, 19 Aug 2026 18:42:11 +0000", as WordPress writes pubDate. */
export function feedDate(iso: string): string {
	return new Date(iso).toUTCString().replace('GMT', '+0000');
}
