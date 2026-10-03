import { xmlrpc } from '$lib/server/wordpress';
import type { RequestHandler } from './$types';

export const trailingSlash = 'ignore';

export const fallback: RequestHandler = ({ request, url }) => xmlrpc(request, url);
