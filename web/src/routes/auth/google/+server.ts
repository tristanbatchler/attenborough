import { redirect } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { startGoogleLogin } from '$lib/client';
import { apiOptions, unwrap } from '$lib/server/api';
import type { RequestHandler } from './$types';

// The admin's way in: off to Google's consent screen, which comes back to ./callback.
export const GET: RequestHandler = async ({ fetch }) => {
	const login = unwrap(await startGoogleLogin(apiOptions(fetch)));
	redirect(constants.HTTP_STATUS_SEE_OTHER, login.url);
};
