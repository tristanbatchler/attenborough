import { redirect, type Cookies, type RequestEvent } from '@sveltejs/kit';
import { randomBytes, randomInt } from 'node:crypto';
import { constants } from 'node:http2';
import { setTimeout as sleep } from 'node:timers/promises';
import { reportLogin, type LoginOutcome } from '$lib/client';
import { apiOptions } from '$lib/server/api';
import { field, postedForm } from '$lib/server/forms';
import { NOCACHE_HEADERS } from '$lib/server/headers';
import { htmlPage } from '$lib/server/html';
import { requestTarget } from '$lib/server/visit';
import { AUTHORS } from '$lib/site/blog';
import LoginPage from '$lib/wordpress/LoginPage.svelte';
import { ADMIN_PATH, LoginError, PASSWORD_FIELD, USERNAME_FIELD } from '$lib/wordpress/site';
import type { RequestHandler } from './$types';

// The cookie WordPress sets on its login page to check that the browser keeps cookies.
const TEST_COOKIE = 'wordpress_test_cookie';
const TEST_COOKIE_VALUE = 'WP Cookie check';
// Where WordPress sets its cookies for the whole site (COOKIEPATH).
const SITE_COOKIE_PATH = '/';
// WordPress's no-cache headers and its frame protection.
const LOGIN_PAGE_HEADERS = { ...NOCACHE_HEADERS, 'x-frame-options': 'SAMEORIGIN' };
const BODY_CLASS = 'login no-js login-action-login wp-core-ui locale-en-us';

function loginPage(cookies: Cookies, username: string, error: LoginError | null): Response {
	cookies.set(TEST_COOKIE, TEST_COOKIE_VALUE, { path: SITE_COOKIE_PATH, httpOnly: false });
	return htmlPage(
		LoginPage,
		{ username, error },
		{ headers: LOGIN_PAGE_HEADERS, bodyClass: BODY_CLASS }
	);
}

// WordPress's login cookies (wp_set_auth_cookie), named after a hash of the site's URL. This one
// is fixed and made up, so it names no domain. The auth cookie goes to the admin area and plugins,
// the logged-in one to the whole site; both last the session, HttpOnly and without SameSite.
const COOKIE_HASH = '0490963b95b41abb5b08057dfebac257';
const AUTH_COOKIE = `wordpress_${COOKIE_HASH}`;
const SECURE_AUTH_COOKIE = `wordpress_sec_${COOKIE_HASH}`;
const LOGGED_IN_COOKIE = `wordpress_logged_in_${COOKIE_HASH}`;
const AUTH_COOKIE_PATHS = ['/wp-content/plugins', ADMIN_PATH.replace(/\/$/, '')];
const HTTPS_PROTOCOL = 'https:';
// The value: `login|expiration|token|hmac`, expiring in two days (2 * DAY_IN_SECONDS, without
// "Remember Me"), with a 43-character session token and a SHA-256 HMAC. Ours are random: nothing
// ever checks them.
// ponytail: "Remember Me" gets the same session cookies; WordPress gives it 14 days and an Expires.
const SESSION_SECONDS = 172_800;
const MS_PER_SECOND = 1000;
const TOKEN_LENGTH = 43;
const TOKEN_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
const HMAC_BYTES = 32;
const HEX = 'hex';

/** The cookies of a login WordPress accepted. They open nothing: /wp-admin/ never reads them. */
function setAuthCookies(event: RequestEvent, username: string): void {
	const secure = event.url.protocol === HTTPS_PROTOCOL;
	const expiration = Math.floor(Date.now() / MS_PER_SECOND) + SESSION_SECONDS;
	const token = Array.from({ length: TOKEN_LENGTH }, () =>
		TOKEN_ALPHABET.charAt(randomInt(TOKEN_ALPHABET.length))
	).join('');
	// The auth and logged-in cookies share all but the HMAC.
	const cookie = () =>
		[username, String(expiration), token, randomBytes(HMAC_BYTES).toString(HEX)].join('|');
	const options = { httpOnly: true, secure, sameSite: false } as const;
	const authName = secure ? SECURE_AUTH_COOKIE : AUTH_COOKIE;
	const authValue = cookie();
	for (const path of AUTH_COOKIE_PATHS) {
		event.cookies.set(authName, authValue, { ...options, path });
	}
	event.cookies.set(LOGGED_IN_COOKIE, cookie(), { ...options, path: SITE_COOKIE_PATH });
}

/** The blog's authors, whose usernames its author archives and REST API give away. */
function isAuthor(username: string): boolean {
	return AUTHORS.some((author) => author.slug === username);
}

/**
 * Record the attempt; the API decides whether it succeeds, and how long to keep the visitor
 * waiting first (its tarpit for persistent guessers). Null when the API couldn't be asked: the
 * login fails.
 */
async function attemptLogin(
	event: RequestEvent,
	username: string,
	password: string
): Promise<LoginOutcome | null> {
	const result = await reportLogin({
		...apiOptions(event),
		body: { path: requestTarget(event).path, username, password }
	});
	if (result.data === undefined) {
		console.error('Failed to report a login attempt', result.error);
		return null;
	}
	await sleep(result.data.delay_ms);
	return result.data;
}

// As in [...path]: no trailing-slash redirects. nginx passes `/wp-login.php/` to PHP as the script.
export const trailingSlash = 'ignore';

// PHP runs wp-login.php for any method, and WordPress shows the login form for anything but a POST.
export const fallback: RequestHandler = ({ cookies }) => loginPage(cookies, '', null);

export const POST: RequestHandler = async (event) => {
	const form = await postedForm(event.request);
	const username = field(form, USERNAME_FIELD) ?? '';
	const password = field(form, PASSWORD_FIELD) ?? '';
	const outcome = form && (await attemptLogin(event, username, password));
	if (outcome?.success) {
		setAuthCookies(event, username);
		redirect(constants.HTTP_STATUS_FOUND, ADMIN_PATH);
	}

	// WordPress checks for empty fields before looking the user up. An account that exists (one an
	// install created, or an author's) gets a wrong password, not "not registered".
	let error: LoginError = LoginError.INVALID_USERNAME;
	if (!username) {
		error = LoginError.EMPTY_USERNAME;
	} else if (!password) {
		error = LoginError.EMPTY_PASSWORD;
	} else if (outcome?.known_account || isAuthor(username)) {
		error = LoginError.INCORRECT_PASSWORD;
	}
	return loginPage(event.cookies, username, error);
};
