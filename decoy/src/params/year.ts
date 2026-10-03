import type { ParamMatcher } from '@sveltejs/kit';

// A permalink's year: four digits.
export const match: ParamMatcher = (param) => /^\d{4}$/.test(param);
