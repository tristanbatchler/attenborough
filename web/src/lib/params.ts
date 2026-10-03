// URL query parameters that pages write (links, forms) and server `load` functions read. Kept
// out of $lib/server so pages can import them too.

/** `?before=`: where a listing's page starts, the API's opaque `next_cursor` from the page before. */
export const BEFORE_PARAM = 'before';

/** `?address=`: the IP address the home page's lookup form submits to /ip. */
export const ADDRESS_PARAM = 'address';

/** The search string (after the `?`) for the page starting at `before`. */
export function beforeSearch(before: string): string {
	return new URLSearchParams({ [BEFORE_PARAM]: before }).toString();
}

/** `?example=`: the rule example (`RULE_EXAMPLES`) a new response rule starts from. */
export const EXAMPLE_PARAM = 'example';
