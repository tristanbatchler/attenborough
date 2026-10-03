import { hasSession } from '$lib/server/admin';
import type { LayoutServerLoad } from './$types';

// Whether to show the admin links (Admin, ban this address) or Log in. Only the cookie's presence,
// never a call to the API: public pages cost nothing more for an admin.
export const load: LayoutServerLoad = ({ cookies }) => ({ admin: hasSession(cookies) });
