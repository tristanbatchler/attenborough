import type { RequestEvent } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { randomInt } from 'node:crypto';
import { reportInstall } from '$lib/client';
import { apiOptions } from '$lib/server/api';
import { field, postedForm } from '$lib/server/forms';
import {
	CONTENT_TYPE_HEADER,
	NOCACHE_HEADERS,
	POWERED_BY_HEADER,
	SETUP_HTML_CONTENT_TYPE
} from '$lib/server/headers';
import { htmlPage } from '$lib/server/html';
import { requestTarget } from '$lib/server/visit';
import { wpDie } from '$lib/server/wp-die';
import {
	DISCOURAGE_SEARCH_ENGINES,
	InstallError,
	type InstallScreen,
	type SetupForm
} from '$lib/wordpress/install';
import InstallPage from '$lib/wordpress/InstallPage.svelte';

// wp-admin/install.php on a site whose database has no tables yet, so anyone can finish the
// install and become its administrator. Bots poll for exactly this. A submission WordPress accepts
// is reported to the API (POST /ingest/installs), which records the account and decides its
// password; this page only shows the outcome. Nothing is installed: the blog and its login stay as
// they were. Every submission, accepted or not, is also in its hit's body.

const STEP_QUERY = 'step';
const InstallStep = { WELCOME: 1, INSTALL: 2 } as const;

const Field = {
	SITE_TITLE: 'weblog_title',
	USERNAME: 'user_name',
	PASSWORD: 'admin_password',
	PASSWORD_AGAIN: 'admin_password2',
	EMAIL: 'admin_email',
	BLOG_PUBLIC: 'blog_public',
	LANGUAGE: 'language'
} as const;

const INSTALL_HEADERS = {
	...NOCACHE_HEADERS,
	...POWERED_BY_HEADER,
	[CONTENT_TYPE_HEADER]: SETUP_HTML_CONTENT_TYPE
};
const BODY_CLASS = 'wp-core-ui';

// The password the setup form suggests: wp_generate_password( 18 ), with its special characters.
const SUGGESTED_PASSWORD_ALPHABET =
	'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()';
const SUGGESTED_PASSWORD_LENGTH = 18;

// What WordPress says when its database can't be reached while installing (wpdb::db_connect), the
// host as the leaked wp-config.php names it: the answer when the API couldn't record the install.
const DATABASE_UNREACHABLE =
	'<h1>Error establishing a database connection</h1>\n' +
	'<p>This either means that the username and password information in your ' +
	'<code>wp-config.php</code> file is incorrect or that contact with the database server at ' +
	'<code>localhost</code> could not be established. This could mean your host&#8217;s database ' +
	'server is down.</p>\n<ul>\n' +
	'<li>Are you sure you have the correct username and password?</li>\n' +
	'<li>Are you sure you have typed the correct hostname?</li>\n' +
	'<li>Are you sure the database server is running?</li>\n</ul>\n' +
	'<p>If you are unsure what these terms mean you should probably contact your host. If you still ' +
	'need help you can always visit the <a href="https://wordpress.org/support/forums/">WordPress ' +
	'support forums</a>.</p>\n';

function suggestPassword(): string {
	return Array.from({ length: SUGGESTED_PASSWORD_LENGTH }, () =>
		SUGGESTED_PASSWORD_ALPHABET.charAt(randomInt(SUGGESTED_PASSWORD_ALPHABET.length))
	).join('');
}

/** PHP's `(int)` of the step: leading digits, anything else 0. */
function step(url: URL): number {
	const parsed = Number.parseInt(url.searchParams.get(STEP_QUERY) ?? '', 10);
	return Number.isNaN(parsed) ? 0 : parsed;
}

// The marks Unicode decomposition separates from a letter (`é` is `e` and an acute accent).
const COMBINING_MARKS = /\p{M}/gu;

/**
 * sanitize_user( $username, true ): tags removed, accents removed (remove_accents(), here by
 * decomposing letters and dropping their marks), %XX octets and entities removed, then anything
 * but letters, digits, space, `_ . - @`, then whitespace trimmed and collapsed. remove_accents()
 * also spells out a few letters decomposition can't (`ß` as `ss`); those are dropped here, which
 * makes no difference to whether a username is accepted: either way it has changed.
 */
function sanitizeUser(username: string): string {
	return username
		.replace(/<[^>]*>/g, '')
		.normalize('NFD')
		.replace(COMBINING_MARKS, '')
		.replace(/%[a-fA-F0-9]{2}/g, '')
		.replace(/&.+?;/g, '')
		.replace(/[^a-z0-9 _.\-@]/gi, '')
		.trim()
		.replace(/\s+/g, ' ');
}

const MIN_EMAIL_LENGTH = 6;
// A domain needs at least a name and a top-level domain.
const MIN_DOMAIN_LABELS = 2;
const EMAIL_LOCAL = /^[a-zA-Z0-9!#$%&'*+/=?^_`{|}~.-]+$/;
const EMAIL_LABEL = /^[a-z0-9-]+$/i;

/** is_email(): WordPress's own checks, which are looser than the RFC. */
function isEmail(email: string): boolean {
	const at = email.indexOf('@', 1);
	if (email.length < MIN_EMAIL_LENGTH || at === -1) {
		return false;
	}
	const local = email.slice(0, at);
	const domain = email.slice(at + 1);
	const labels = domain.split('.');
	return (
		EMAIL_LOCAL.test(local) &&
		!domain.includes('..') &&
		labels.length >= MIN_DOMAIN_LABELS &&
		labels.every(
			(label) => EMAIL_LABEL.test(label) && !label.startsWith('-') && !label.endsWith('-')
		)
	);
}

function setupForm(form: FormData | null, url: URL): SetupForm {
	const password = field(form, Field.PASSWORD);
	return {
		siteTitle: field(form, Field.SITE_TITLE)?.trim() ?? '',
		username: sanitizeUser(field(form, Field.USERNAME)?.trim() ?? ''),
		email: field(form, Field.EMAIL)?.trim() ?? '',
		initialPassword: password ?? suggestPassword(),
		passwordSubmitted: password !== null,
		// Indexed unless a submitted form says otherwise.
		discourageSearchEngines:
			field(form, Field.SITE_TITLE) !== null &&
			field(form, Field.BLOG_PUBLIC) === DISCOURAGE_SEARCH_ENGINES,
		language: field(form, Field.LANGUAGE) ?? url.searchParams.get(Field.LANGUAGE) ?? ''
	};
}

/** Step 2: the submission, checked as install.php checks it, in its order, then "installed". */
async function install(
	event: RequestEvent,
	form: FormData | null
): Promise<InstallScreen | Response> {
	const siteTitle = field(form, Field.SITE_TITLE)?.trim() ?? '';
	const username = field(form, Field.USERNAME)?.trim() ?? '';
	const password = field(form, Field.PASSWORD) ?? '';
	const passwordAgain = field(form, Field.PASSWORD_AGAIN) ?? '';
	const email = field(form, Field.EMAIL)?.trim() ?? '';

	let error: InstallError | null = null;
	if (!username) {
		error = InstallError.NO_USERNAME;
	} else if (sanitizeUser(username) !== username) {
		error = InstallError.INVALID_USERNAME;
	} else if (password !== passwordAgain) {
		error = InstallError.PASSWORD_MISMATCH;
	} else if (!email) {
		error = InstallError.NO_EMAIL;
	} else if (!isEmail(email)) {
		error = InstallError.INVALID_EMAIL;
	}
	if (error !== null) {
		return { kind: 'error', error, form: setupForm(form, event.url) };
	}
	const result = await reportInstall({
		...apiOptions(event),
		body: { path: requestTarget(event).path, site_title: siteTitle, username, email, password }
	});
	if (result.data === undefined) {
		console.error('Failed to report an install', result.error);
		return wpDie(DATABASE_UNREACHABLE, constants.HTTP_STATUS_INTERNAL_SERVER_ERROR);
	}
	return { kind: 'success', username, generatedPassword: result.data.generated_password };
}

/** wp-admin/install.php, for any method: PHP reads the step from the query, the form from $_POST. */
export async function installer(event: RequestEvent): Promise<Response> {
	const form = await postedForm(event.request);
	const current = step(event.url);
	let screen: InstallScreen | Response = { kind: 'blank' };
	// Step 0 is the language chooser, which falls through to step 1 without translations.
	if (current === 0 || current === InstallStep.WELCOME) {
		screen = { kind: 'welcome', form: setupForm(form, event.url) };
	} else if (current === InstallStep.INSTALL) {
		screen = await install(event, form);
	}
	if (screen instanceof Response) {
		return screen;
	}
	return htmlPage(InstallPage, { screen }, { headers: INSTALL_HEADERS, bodyClass: BODY_CLASS });
}
