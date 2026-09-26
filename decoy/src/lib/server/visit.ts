import type { RequestEvent } from '@sveltejs/kit';

// What the visitor sent, captured before the request is served and reported to the API as is.

const QUERY_SEPARATOR = '?';

export interface Visit {
	method: string;
	/** The request line's path exactly as sent: not decoded or normalised. */
	path: string;
	/** After the first `?`, as sent; null when there was none. */
	query: string | null;
	headers: Record<string, string>;
	/** The whole body; null if it couldn't be read (see readBody). */
	body: Uint8Array | null;
}

/**
 * The request target exactly as sent. SvelteKit's `event.url` is parsed and normalised
 * (`/cgi-bin/.%2e/.%2e/etc/passwd` becomes `/etc/passwd`), so this reads adapter-node's raw
 * `req.url` instead, which Node decodes one character per byte, as the API does. `vite dev` has no
 * Node request, so there it falls back to the parsed URL.
 */
function requestTarget(event: RequestEvent): { path: string; query: string | null } {
	const raw = event.platform?.req.url;
	if (raw === undefined) {
		return {
			path: event.url.pathname,
			query: event.url.search ? event.url.search.slice(1) : null
		};
	}
	const separator = raw.indexOf(QUERY_SEPARATOR);
	return separator === -1
		? { path: raw, query: null }
		: { path: raw.slice(0, separator), query: raw.slice(separator + 1) };
}

/**
 * The body, read from a copy so the route can still read the original. Null if it can't be read:
 * adapter-node refuses a body over BODY_SIZE_LIMIT before reading any of it, and recording it as
 * empty would be wrong.
 */
async function readBody(request: Request): Promise<Uint8Array | null> {
	try {
		return new Uint8Array(await request.clone().arrayBuffer());
	} catch (error) {
		console.error('Could not read a request body', error);
		return null;
	}
}

export async function captureVisit(event: RequestEvent): Promise<Visit> {
	return {
		method: event.request.method,
		...requestTarget(event),
		headers: Object.fromEntries(event.request.headers),
		body: await readBody(event.request)
	};
}
