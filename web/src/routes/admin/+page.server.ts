import { listActiveBans } from '$lib/client';
import { adminOptions, unwrapAdmin } from '$lib/server/admin';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, cookies }) => ({
	bans: unwrapAdmin(await listActiveBans(adminOptions(fetch, cookies)))
});
