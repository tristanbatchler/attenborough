import { listAuditLog } from '$lib/client';
import { adminOptions, unwrapAdmin } from '$lib/server/admin';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, cookies }) => ({
	entries: unwrapAdmin(await listAuditLog(adminOptions(fetch, cookies)))
});
