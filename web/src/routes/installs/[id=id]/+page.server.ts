import { getTakeover } from '$lib/client';
import { apiOptions, unwrap } from '$lib/server/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params, fetch }) => {
	const takeover = unwrap(
		await getTakeover({ ...apiOptions(fetch), path: { install_id: Number(params.id) } }),
		'There is no such install.'
	);
	return { takeover };
};
