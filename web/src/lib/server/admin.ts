import { error, type Cookies } from '@sveltejs/kit';
import { constants } from 'node:http2';
import type { Session } from '$lib/client';
import { apiOptions, unwrap, type ApiResult } from '$lib/server/api';

// The admin area's side of the login (api/src/attenborough/auth.py). The API gives the web server a
// session token, which it keeps in a cookie on the exhibit's own origin and sends back to the API as
// a bearer token on every admin call. The public exhibit never reads it.

// SvelteKit's defaults make it HttpOnly, SameSite=Lax and Secure (except on http://localhost).
const SESSION_COOKIE = 'session';
const COOKIE_PATH = '/';
// What SvelteKit answers a path no route matches. Anyone who isn't logged in as an admin gets the
// same for every admin page, so nothing confirms that the admin area exists.
const NOT_FOUND_MESSAGE = 'Not Found';

/** Admin pages are never cached, by the browser or anything in between. */
export const PRIVATE_PAGE_HEADERS = { 'cache-control': 'private, no-store' };

/** The answer to anyone who isn't an admin: the same 404 as an unknown path. */
export function notFound(): never {
	error(constants.HTTP_STATUS_NOT_FOUND, NOT_FOUND_MESSAGE);
}

/** Options for an admin SDK call: `apiOptions`, and the session as a bearer token. 404 without one. */
export function adminOptions(fetch: typeof globalThis.fetch, cookies: Cookies) {
	const token = cookies.get(SESSION_COOKIE);
	if (token === undefined) {
		notFound();
	}
	return { ...apiOptions(fetch), auth: token };
}

/** `unwrap` for the admin API, whose 404 means "not an admin": the unknown-path 404. */
export function unwrapAdmin<T>(result: ApiResult<T>, invalidInput?: string): T {
	if (result.response?.status === constants.HTTP_STATUS_NOT_FOUND) {
		notFound();
	}
	return unwrap(result, invalidInput);
}

/**
 * Whether the visitor has a session cookie, for the public pages' admin links. Read without asking
 * the API, so it can be stale; every admin page checks it with the API, and forgets a stale one.
 */
export function hasSession(cookies: Cookies): boolean {
	return cookies.get(SESSION_COOKIE) !== undefined;
}

export function startSession(cookies: Cookies, session: Session): void {
	cookies.set(SESSION_COOKIE, session.token, {
		path: COOKIE_PATH,
		expires: new Date(session.expires_at)
	});
}

/** The session's token, if there is one, and forgets it. */
export function endSession(cookies: Cookies): string | undefined {
	const token = cookies.get(SESSION_COOKIE);
	cookies.delete(SESSION_COOKIE, { path: COOKIE_PATH });
	return token;
}

/** A text field of a submitted form, trimmed; null when empty or missing. */
export function textField(form: FormData, name: string): string | null {
	const value = form.get(name);
	return typeof value === 'string' && value.trim() !== '' ? value.trim() : null;
}
