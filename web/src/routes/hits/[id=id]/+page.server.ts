import { getHit } from '$lib/client';
import { apiOptions, unwrap } from '$lib/server/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params, fetch }) => {
	const hit = unwrap(
		await getHit({ ...apiOptions(fetch), path: { hit_id: Number(params.id) } }),
		'There is no such request.'
	);
	return { hit };
};
