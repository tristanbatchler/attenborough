import { robots } from '$lib/server/blog';
import type { RequestHandler } from './$types';

export const fallback: RequestHandler = () => robots();
