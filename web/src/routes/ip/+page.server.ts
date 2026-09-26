import { redirect } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { ADDRESS_PARAM } from '$lib/params';
import type { PageServerLoad } from './$types';

// Target of the home page's lookup form (GET /ip?address=...), which works without JavaScript.
export const load: PageServerLoad = ({ url }) => {
	const address = url.searchParams.get(ADDRESS_PARAM)?.trim();
	redirect(constants.HTTP_STATUS_SEE_OTHER, address ? `/ip/${encodeURIComponent(address)}` : '/');
};
