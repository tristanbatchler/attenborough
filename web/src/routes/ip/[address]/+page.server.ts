import { getIpActivity } from '$lib/client';
import { apiOptions, unwrap } from '$lib/server/api';
import { requestedPage } from '$lib/server/paging';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params, url, fetch }) => {
	const page = requestedPage(url);
	const activity = unwrap(
		await getIpActivity({
			...apiOptions(fetch),
			path: { ip_addr: params.address },
			query: { page }
		}),
		'That is not a valid IP address, or that page does not exist.'
	);
	return { address: params.address, page, activity };
};
