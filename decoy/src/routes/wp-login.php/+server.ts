import { redirect, type Cookies, type RequestEvent } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { loginsAttemptLogin } from '$lib/client';
import { apiOptions } from '$lib/server/api';
import { CONTENT_TYPE_HEADER } from '$lib/server/headers';
import { htmlPage } from '$lib/server/html';
import LoginPage from '$lib/wordpress/LoginPage.svelte';
import { ADMIN_PATH, LoginError, PASSWORD_FIELD, USERNAME_FIELD } from '$lib/wordpress/site';
import type { RequestHandler } from './$types';

// The cookie WordPress sets on its login page to check that the browser keeps cookies.
const TEST_COOKIE = 'wordpress_test_cookie';
const TEST_COOKIE_VALUE = 'WP Cookie check';
// WordPress's no-cache headers (wp_get_nocache_headers) and its frame protection.
const LOGIN_PAGE_HEADERS = {
	'cache-control': 'no-cache, must-revalidate, max-age=0',
	expires: 'Wed, 11 Jan 1984 05:00:00 GMT',
	'x-frame-options': 'SAMEORIGIN'
};
const BODY_CLASS = 'login no-js login-action-login wp-core-ui locale-en-us';
// PHP fills $_POST, where WordPress reads the login form, only for these content types. Any other
// POST (JSON, XML, credentials in the query string) looks empty to it. The body is still recorded
// with the hit, so nothing sent this way is lost.
const FORM_CONTENT_TYPES = ['application/x-www-form-urlencoded', 'multipart/form-data'];

function loginPage(cookies: Cookies, username: string, error: LoginError | null): Response {
	cookies.set(TEST_COOKIE, TEST_COOKIE_VALUE, { path: '/', httpOnly: false });
	return htmlPage(
		LoginPage,
		{ username, error },
		{ headers: LOGIN_PAGE_HEADERS, bodyClass: BODY_CLASS }
	);
}

/** The posted form, as PHP would see it: null for anything that isn't a form post. */
async function postedForm(request: Request): Promise<FormData | null> {
	const contentType = request.headers.get(CONTENT_TYPE_HEADER) ?? '';
	if (!FORM_CONTENT_TYPES.some((type) => contentType.startsWith(type))) {
		return null;
	}
	try {
		return await request.formData();
	} catch {
		// A malformed form: PHP ignores what it can't parse.
		return null;
	}
}

/** A submitted text field, or '' if it is missing or a file. */
function field(form: FormData | null, name: string): string {
	const value = form?.get(name);
	return typeof value === 'string' ? value : '';
}

/** Record the attempt; the API decides whether it succeeds. */
async function attemptLogin(event: RequestEvent, username: string, password: string) {
	const result = await loginsAttemptLogin({
		...apiOptions(event),
		body: { path: event.url.pathname, username, password }
	});
	if (result.data === undefined) {
		console.error('Failed to report a login attempt', result.error);
		return false;
	}
	return result.data.success;
}

// As in [...path]: no trailing-slash redirects. nginx passes `/wp-login.php/` to PHP as the script.
export const trailingSlash = 'ignore';

// PHP runs wp-login.php for any method, and WordPress shows the login form for anything but a POST.
export const fallback: RequestHandler = ({ cookies }) => loginPage(cookies, '', null);

export const POST: RequestHandler = async (event) => {
	const form = await postedForm(event.request);
	const username = field(form, USERNAME_FIELD);
	const password = field(form, PASSWORD_FIELD);
	if (form && (await attemptLogin(event, username, password))) {
		redirect(constants.HTTP_STATUS_FOUND, ADMIN_PATH);
	}

	// WordPress checks for empty fields before looking the user up.
	let error: LoginError = LoginError.INVALID_USERNAME;
	if (!username) {
		error = LoginError.EMPTY_USERNAME;
	} else if (!password) {
		error = LoginError.EMPTY_PASSWORD;
	}
	return loginPage(event.cookies, username, error);
};
