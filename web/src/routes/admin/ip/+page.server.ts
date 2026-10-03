import { redirect } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { resolve } from '$app/paths';
import { ADDRESS_PARAM } from '$lib/params';
import type { PageServerLoad } from './$types';

// Target of the admin page's address form (GET /admin/ip?address=...), as /ip is the exhibit's.
export const load: PageServerLoad = async ({ url, parent }) => {
	// The layout's admin check first: anyone else must get its 404, not a redirect.
	await parent();
	const address = url.searchParams.get(ADDRESS_PARAM)?.trim();
	redirect(
		constants.HTTP_STATUS_SEE_OTHER,
		address ? resolve('/admin/ip/[address]', { address }) : resolve('/admin')
	);
};
