import type { ParamMatcher } from '@sveltejs/kit';

// A permalink's month: two digits.
export const match: ParamMatcher = (param) => /^\d{2}$/.test(param);
