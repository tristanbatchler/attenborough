import { constants } from 'node:http2';
import { postPage } from '$lib/server/blog';
import { nginxError } from '$lib/server/nginx';
import { postAt } from '$lib/site/blog';
import type { RequestHandler } from './$types';

// A post's permalink, /2026/08/<slug>/.
export const trailingSlash = 'ignore';

export const fallback: RequestHandler = ({ params }) => {
	const post = postAt(params.year, params.month, params.slug);
	return post ? postPage(post) : nginxError(constants.HTTP_STATUS_NOT_FOUND);
};
