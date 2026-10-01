import type { ParamMatcher } from '@sveltejs/kit';

/** A record id: a whole number written plainly, and small enough to be exact in JavaScript. */
export const match = ((param: string) => {
	const id = Number(param);
	return Number.isSafeInteger(id) && String(id) === param;
}) satisfies ParamMatcher;
