import {
	CONTENT_TYPE_HEADER,
	NOCACHE_HEADERS,
	POWERED_BY_HEADER,
	SETUP_HTML_CONTENT_TYPE
} from '$lib/server/headers';

// WordPress's error page, wp_die() (_default_wp_die_handler), shortened to the styles that show.
// `message` is markup, so it is only ever fixed content: nothing a visitor sent goes into it.

const STYLE =
	'\t\thtml { background: #f1f1f1; }\n' +
	'\t\tbody { background: #fff; border: 1px solid #ccd0d4; color: #444; ' +
	'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen-Sans, Ubuntu, ' +
	'Cantarell, "Helvetica Neue", sans-serif; margin: 2em auto; padding: 1em 2em; max-width: 700px; ' +
	'box-shadow: 0 1px 1px rgba(0, 0, 0, .04); }\n' +
	'\t\th1 { border-bottom: 1px solid #dadada; clear: both; color: #666; font-size: 24px; ' +
	'margin: 30px 0 0 0; padding: 0; padding-bottom: 7px; }\n' +
	'\t\t#error-page { margin-top: 50px; }\n' +
	'\t\t#error-page p, #error-page .wp-die-message { font-size: 14px; line-height: 1.5; ' +
	'margin: 25px 0 20px; }\n' +
	'\t\t#error-page code { font-family: Consolas, Monaco, monospace; }\n' +
	'\t\tul li { margin-bottom: 10px; font-size: 14px ; }\n' +
	'\t\ta { color: #2271b1; }\n';

/** wp_die( $message ) with the given status: the page, its status and WordPress's headers. */
export function wpDie(message: string, status: number): Response {
	const html =
		"<!DOCTYPE html>\n<html dir='ltr'>\n<head>\n" +
		'\t<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />\n' +
		'\t<meta name="viewport" content="width=device-width">\n' +
		"\t<meta name='robots' content='max-image-preview:large, noindex, follow' />\n" +
		`\t<title>WordPress &rsaquo; Error</title>\n\t<style type="text/css">\n${STYLE}` +
		'\t</style>\n</head>\n<body id="error-page">\n' +
		`\t<div class="wp-die-message">${message}</div></body>\n</html>\n`;
	return new Response(html, {
		status,
		headers: {
			...NOCACHE_HEADERS,
			...POWERED_BY_HEADER,
			[CONTENT_TYPE_HEADER]: SETUP_HTML_CONTENT_TYPE
		}
	});
}
