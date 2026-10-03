import { adminPage } from '$lib/server/wordpress';
import type { RequestHandler } from './$types';

export const trailingSlash = 'ignore';

export const fallback: RequestHandler = ({ params }) => adminPage(params.rest);
