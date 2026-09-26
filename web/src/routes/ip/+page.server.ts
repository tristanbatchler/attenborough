import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

// Target of the home page's lookup form (GET /ip?address=...), which works without JavaScript.
export const load: PageServerLoad = ({ url }) => {
	const address = url.searchParams.get('address')?.trim();
	redirect(303, address ? `/ip/${encodeURIComponent(address)}` : '/');
};
