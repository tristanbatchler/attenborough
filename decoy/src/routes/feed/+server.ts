import { feed } from '$lib/server/blog';
import type { RequestHandler } from './$types';

export const trailingSlash = 'ignore';

export const fallback: RequestHandler = () => feed();
