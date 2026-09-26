import { feedListRecent } from '$lib/client';
import { apiOptions, unwrap } from '$lib/server/api';
import { paging } from '$lib/server/paging';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ url, fetch }) => {
	const api = apiOptions(fetch);
	const { page, take } = await paging(url, api);
	const rows = unwrap(await feedListRecent({ ...api, query: { page, take } }));

	return {
		page,
		rows,
		// A full page means there may be more; the API has no total count yet.
		hasNextPage: rows.length === take
	};
};
