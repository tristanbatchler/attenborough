import { home } from '$lib/server/blog';
import type { RequestHandler } from './$types';

// The front page, which WordPress also routes by query (`?rest_route=`, `?author=`, `?feed=`).
export const fallback: RequestHandler = ({ url }) => home(url);
