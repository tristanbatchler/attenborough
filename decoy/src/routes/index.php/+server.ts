import { home } from '$lib/server/blog';
import type { RequestHandler } from './$types';

// As nginx passes it to PHP: the same script as `/`.
export const trailingSlash = 'ignore';

export const fallback: RequestHandler = ({ request, url }) => home(request, url);
