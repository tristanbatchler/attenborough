import { STATUS_CODES } from 'node:http';
import { CONTENT_TYPE_HEADER } from '$lib/server/headers';

// What the imitated server's own error pages name it: nginx's default, with server_tokens off.
const SERVER = 'nginx';

/** nginx's built-in error page for `status`, byte for byte, as it answers unknown paths. */
export function nginxError(status: number): Response {
	const title = `${String(status)} ${STATUS_CODES[status] ?? ''}`;
	const html =
		`<html>\r\n<head><title>${title}</title></head>\r\n<body>\r\n` +
		`<center><h1>${title}</h1></center>\r\n<hr><center>${SERVER}</center>\r\n</body>\r\n</html>\r\n`;
	return new Response(html, { status, headers: { [CONTENT_TYPE_HEADER]: 'text/html' } });
}
