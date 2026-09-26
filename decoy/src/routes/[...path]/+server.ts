import { constants } from 'node:http2';
import { nginxError } from '$lib/server/nginx';
import type { RequestHandler } from './$types';

// SvelteKit would otherwise redirect `/phpmyadmin/` to `/phpmyadmin` before the handle hook runs:
// a redirect nginx never sends, and a request that would go unreported.
export const trailingSlash = 'ignore';

// Every path no decoy serves, whatever the method: nginx's own 404, as a real server sends.
export const fallback: RequestHandler = () => nginxError(constants.HTTP_STATUS_NOT_FOUND);
