import { xmlrpc } from '$lib/server/xmlrpc';
import type { RequestHandler } from './$types';

export const trailingSlash = 'ignore';

export const fallback: RequestHandler = (event) => xmlrpc(event);
