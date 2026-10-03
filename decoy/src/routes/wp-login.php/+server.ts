import { redirect, type Cookies, type RequestEvent } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { setTimeout as sleep } from 'node:timers/promises';
import { reportLogin } from '$lib/client';
import { apiOptions } from '$lib/server/api';
import { field, postedForm } from '$lib/server/forms';
import { NOCACHE_HEADERS } from '$lib/server/headers';
import { htmlPage } from '$lib/server/html';
import { requestTarget } from '$lib/server/visit';
import LoginPage from '$lib/wordpress/LoginPage.svelte';
import { ADMIN_PATH, LoginError, PASSWORD_FIELD, USERNAME_FIELD } from '$lib/wordpress/site';
import type { RequestHandler } from './$types';

// The cookie WordPress sets on its login page to check that the browser keeps cookies.
const TEST_COOKIE = 'wordpress_test_cookie';
const TEST_COOKIE_VALUE = 'WP Cookie check';
// WordPress's no-cache headers and its frame protection.
const LOGIN_PAGE_HEADERS = { ...NOCACHE_HEADERS, 'x-frame-options': 'SAMEORIGIN' };
const BODY_CLASS = 'login no-js login-action-login wp-core-ui locale-en-us';

function loginPage(cookies: Cookies, username: string, error: LoginError | null): Response {
	cookies.set(TEST_COOKIE, TEST_COOKIE_VALUE, { path: '/', httpOnly: false });
	return htmlPage(
		LoginPage,
		{ username, error },
		{ headers: LOGIN_PAGE_HEADERS, bodyClass: BODY_CLASS }
	);
}

/**
 * Record the attempt; the API decides whether it succeeds, and how long to keep the visitor
 * waiting first (its tarpit for persistent guessers).
 */
async function attemptLogin(event: RequestEvent, username: string, password: string) {
	const result = await reportLogin({
		...apiOptions(event),
		body: { path: requestTarget(event).path, username, password }
	});
	if (result.data === undefined) {
		console.error('Failed to report a login attempt', result.error);
		return false;
	}
	await sleep(result.data.delay_ms);
	return result.data.success;
}

// As in [...path]: no trailing-slash redirects. nginx passes `/wp-login.php/` to PHP as the script.
export const trailingSlash = 'ignore';

// PHP runs wp-login.php for any method, and WordPress shows the login form for anything but a POST.
export const fallback: RequestHandler = ({ cookies }) => loginPage(cookies, '', null);

export const POST: RequestHandler = async (event) => {
	const form = await postedForm(event.request);
	const username = field(form, USERNAME_FIELD) ?? '';
	const password = field(form, PASSWORD_FIELD) ?? '';
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
