import { constants } from 'node:http2';
import { leak } from '$lib/server/leaks';
import { nginxError } from '$lib/server/nginx';
import type { RequestHandler } from './$types';

// SvelteKit would otherwise redirect `/phpmyadmin/` to `/phpmyadmin` before the handle hook runs:
// a redirect nginx never sends, and a request that would go unreported.
export const trailingSlash = 'ignore';

// Every path no decoy route serves, whatever the method: a leaked file if one was left there
// ($lib/server/leaks), otherwise nginx's own 404, as a real server sends.
export const fallback: RequestHandler = async (event) =>
	(await leak(event, `/${event.params.path}`)) ?? nginxError(constants.HTTP_STATUS_NOT_FOUND);
