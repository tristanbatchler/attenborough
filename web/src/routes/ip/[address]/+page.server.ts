import { error } from '@sveltejs/kit';
import { ipGetIpActivity, metaGetMeta } from '$lib/client';
import { apiOptions, unwrap } from '$lib/server/api';
import type { PageServerLoad } from './$types';

const PAGE_PARAM = 'page';
const FIRST_PAGE = 1;

export const load: PageServerLoad = async ({ params, url, fetch }) => {
	const page = Number(url.searchParams.get(PAGE_PARAM) ?? FIRST_PAGE);
	if (!Number.isInteger(page) || page < FIRST_PAGE) {
		error(400, 'Page must be a whole number, starting from 1.');
	}

	const api = apiOptions(fetch);
	// The page size is the API's setting (APP_DEFAULT_PAGE_TAKE), not the frontend's.
	const { default_page_take: take } = unwrap(await metaGetMeta(api));
	const rows = unwrap(
		await ipGetIpActivity({ ...api, path: { ip_addr: params.address }, query: { page, take } }),
		'That is not a valid IP address.'
	);

	return {
		address: params.address,
		page,
		rows,
		// A full page means there may be more; the API has no total count yet.
		hasNextPage: rows.length === take
	};
};
