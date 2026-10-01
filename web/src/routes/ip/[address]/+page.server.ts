import { getIpEvents, getIpSummary } from '$lib/client';
import { apiOptions, unwrap } from '$lib/server/api';
import { requestedCursor } from '$lib/server/paging';
import type { PageServerLoad } from './$types';

const INVALID_INPUT = 'That is not a valid IP address, or that page does not exist.';

export const load: PageServerLoad = async ({ params, url, fetch }) => {
	const before = requestedCursor(url);
	const path = { ip_addr: params.address };
	const [events, summary] = await Promise.all([
		getIpEvents({ ...apiOptions(fetch), path, query: { before } }),
		getIpSummary({ ...apiOptions(fetch), path })
	]);
	return {
		address: params.address,
		isFirstPage: before === undefined,
		events: unwrap(events, INVALID_INPUT),
		summary: unwrap(summary, INVALID_INPUT)
	};
};
