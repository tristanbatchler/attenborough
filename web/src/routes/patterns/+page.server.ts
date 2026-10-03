import { getPatterns } from '$lib/client';
import { apiOptions, unwrap } from '$lib/server/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
	return { patterns: unwrap(await getPatterns(apiOptions(fetch))) };
};
