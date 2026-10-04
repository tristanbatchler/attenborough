// URL query parameters that pages write (links, forms) and server `load` functions read. Kept
// out of $lib/server so pages can import them too.

/** `?before=`: where a listing's page starts, the API's opaque `next_cursor` from the page before. */
export const BEFORE_PARAM = 'before';

/** `?address=`: an IP address the admin area's forms submit. */
export const ADDRESS_PARAM = 'address';

/** `?q=`: the home page's search, in the API's search syntax (search.py), passed on as is. */
export const SEARCH_PARAM = 'q';

/** The search string (after the `?`) for the page starting at `before`. */
export function beforeSearch(before: string): string {
	return new URLSearchParams({ [BEFORE_PARAM]: before }).toString();
}

/** The search string (after the `?`) of `params`, leaving out the empty and undefined ones. */
export function searchString(params: Record<string, string | undefined>): string {
	const given = Object.entries(params).filter((entry): entry is [string, string] => !!entry[1]);
	return new URLSearchParams(given).toString();
}

/** `?example=`: the rule example (`RULE_EXAMPLES`) a new response rule starts from. */
export const EXAMPLE_PARAM = 'example';
