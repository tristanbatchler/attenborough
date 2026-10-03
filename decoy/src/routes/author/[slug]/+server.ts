import { constants } from 'node:http2';
import { authorPage } from '$lib/server/blog';
import { nginxError } from '$lib/server/nginx';
import { authorBySlug } from '$lib/site/blog';
import type { RequestHandler } from './$types';

// An author's archive, where `?author=N` redirects.
export const trailingSlash = 'ignore';

export const fallback: RequestHandler = ({ params }) => {
	const author = authorBySlug(params.slug);
	return author ? authorPage(author) : nginxError(constants.HTTP_STATUS_NOT_FOUND);
};
