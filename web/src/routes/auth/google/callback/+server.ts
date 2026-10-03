import { redirect } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { resolve } from '$app/paths';
import { finishGoogleLogin } from '$lib/client';
import { apiOptions } from '$lib/server/api';
import { notFound, startSession, unwrapAdmin } from '$lib/server/admin';
import type { RequestHandler } from './$types';

// Google's query parameters on the way back from its consent screen.
const CODE_PARAM = 'code';
const STATE_PARAM = 'state';

// Where Google sends the admin back (the API's WEB_BASE_URL + this path). The API checks the login
// and starts a session for an admin; anyone else gets the unknown-path 404.
export const GET: RequestHandler = async ({ url, fetch, cookies }) => {
	const code = url.searchParams.get(CODE_PARAM);
	const state = url.searchParams.get(STATE_PARAM);
	if (code === null || state === null) {
		notFound();
	}
	const session = unwrapAdmin(
		await finishGoogleLogin({ ...apiOptions(fetch), body: { code, state } })
	);
	startSession(cookies, session);
	redirect(constants.HTTP_STATUS_SEE_OTHER, resolve('/admin'));
};
