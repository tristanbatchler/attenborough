import { readme } from '$lib/server/wordpress';
import type { RequestHandler } from './$types';

export const fallback: RequestHandler = () => readme();
