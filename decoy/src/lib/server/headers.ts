import { POWERED_BY } from '$lib/site/blog';

// HTTP header names and values the decoys set or read.

export const CONTENT_TYPE_HEADER = 'content-type';

// The content types PHP and WordPress send.
export const HTML_CONTENT_TYPE = 'text/html; charset=UTF-8';
/** What the installer and wp_die() write themselves, in lower case. */
export const SETUP_HTML_CONTENT_TYPE = 'text/html; charset=utf-8';
export const TEXT_CONTENT_TYPE = 'text/plain; charset=UTF-8';
export const XML_CONTENT_TYPE = 'text/xml; charset=UTF-8';
export const RSS_CONTENT_TYPE = 'application/rss+xml; charset=UTF-8';
export const JSON_CONTENT_TYPE = 'application/json; charset=UTF-8';

/** What WordPress sends to stop a page being cached (wp_get_nocache_headers, logged out). */
export const NOCACHE_HEADERS = {
	'cache-control': 'no-cache, must-revalidate, max-age=0',
	expires: 'Wed, 11 Jan 1984 05:00:00 GMT'
};

/** What nginx's PHP-FPM backend adds to every page PHP generates. */
export const POWERED_BY_HEADER = { 'x-powered-by': POWERED_BY };
