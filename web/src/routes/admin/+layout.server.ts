import { getMe } from '$lib/client';
import { constants } from 'node:http2';
import {
	adminOptions,
	endSession,
	notFound,
	PRIVATE_PAGE_HEADERS,
	unwrapAdmin
} from '$lib/server/admin';
import type { LayoutServerLoad } from './$types';

// Every admin page: only for a logged-in admin, and the unknown-path 404 for anyone else. The API
// checks the session again on each of a page's own calls, form actions included. A cookie whose
// session has ended (expired, logged out elsewhere) is forgotten, so the nav offers to log in again.
export const load: LayoutServerLoad = async ({ fetch, cookies, setHeaders }) => {
	setHeaders(PRIVATE_PAGE_HEADERS);
	const me = await getMe(adminOptions(fetch, cookies));
	if (me.response?.status === constants.HTTP_STATUS_NOT_FOUND) {
		endSession(cookies);
		notFound();
	}
	return { me: unwrapAdmin(me) };
};
