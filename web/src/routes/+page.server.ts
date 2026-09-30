import { listRecentActivity } from '$lib/client';
import { apiOptions, unwrap } from '$lib/server/api';
import { requestedPage } from '$lib/server/paging';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ url, fetch }) => {
	const page = requestedPage(url);
	const activity = unwrap(
		await listRecentActivity({ ...apiOptions(fetch), query: { page } }),
		'That page does not exist.'
	);
	return { page, activity };
};
