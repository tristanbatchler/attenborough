import { error } from '@sveltejs/kit';
import { ipGetIpActivity } from '$lib/client';
import { apiOptions } from '$lib/server/api';
import type { PageServerLoad } from './$types';

const PAGE_SIZE = 20;
const PAGE_PARAM = 'page';
const FIRST_PAGE = 1;
const HTTP_UNPROCESSABLE_CONTENT = 422;

export const load: PageServerLoad = async ({ params, url, fetch }) => {
	const page = Number(url.searchParams.get(PAGE_PARAM) ?? FIRST_PAGE);
	if (!Number.isInteger(page) || page < FIRST_PAGE) {
		error(400, 'Page must be a whole number, starting from 1.');
	}

	const {
		data,
		error: apiError,
		response
	} = await ipGetIpActivity({
		...apiOptions(fetch),
		path: { ip_addr: params.address },
		query: { page, take: PAGE_SIZE }
	});

	if (data === undefined) {
		if (response === undefined) {
			// No HTTP response at all: the API is unreachable (connection refused, DNS, ...).
			console.error('Exhibit API unreachable', apiError);
			error(503, 'The exhibit is temporarily unavailable.');
		}
		if (response.status === HTTP_UNPROCESSABLE_CONTENT) {
			error(400, 'That is not a valid IP address.');
		}
		console.error('Exhibit API error', response.status, apiError);
		error(502, 'The exhibit could not load this address.');
	}

	return {
		address: params.address,
		page,
		pageSize: PAGE_SIZE,
		rows: data,
		// A full page means there may be more; the API has no total count yet.
		hasNextPage: data.length === PAGE_SIZE
	};
};
