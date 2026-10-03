import { rest } from '$lib/server/blog';
import type { RequestHandler } from './$types';

// The REST API: `/wp-json/` is its index, `/wp-json/wp/v2/users` the authors.
export const trailingSlash = 'ignore';

export const fallback: RequestHandler = ({ params }) => rest(`/${params.route}`);
