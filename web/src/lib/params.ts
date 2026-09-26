// URL query parameters that pages write (links, forms) and server `load` functions read. Kept
// out of $lib/server so pages can import them too.

/** `?page=`: which page of a paginated listing. */
export const PAGE_PARAM = 'page';

/** `?address=`: the IP address the home page's lookup form submits to /ip. */
export const ADDRESS_PARAM = 'address';

/** Pages are numbered from 1. */
export const FIRST_PAGE = 1;
