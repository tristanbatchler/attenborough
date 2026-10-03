import { redirect } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { resolve } from '$app/paths';
import { logOut } from '$lib/client';
import { apiOptions } from '$lib/server/api';
import { endSession } from '$lib/server/admin';
import type { RequestHandler } from './$types';

// The admin layout's "Log out" form. SvelteKit refuses form posts from other origins.
export const POST: RequestHandler = async ({ fetch, cookies }) => {
	const token = endSession(cookies);
	if (token !== undefined) {
		const result = await logOut({ ...apiOptions(fetch), auth: token });
		// The cookie is gone either way; an expired session is simply over already.
		if (
			result.response?.ok !== true &&
			result.response?.status !== constants.HTTP_STATUS_NOT_FOUND
		) {
			console.error('Failed to end a session', result.response?.status, result.error);
		}
	}
	redirect(constants.HTTP_STATUS_SEE_OTHER, resolve('/'));
};
