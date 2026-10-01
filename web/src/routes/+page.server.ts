import { listRecentEvents } from '$lib/client';
import { apiOptions, unwrap } from '$lib/server/api';
import { requestedCursor } from '$lib/server/paging';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ url, fetch }) => {
	const before = requestedCursor(url);
	const events = unwrap(
		await listRecentEvents({ ...apiOptions(fetch), query: { before } }),
		'That page does not exist.'
	);
	return { isFirstPage: before === undefined, events };
};
