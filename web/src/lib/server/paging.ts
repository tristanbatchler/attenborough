import { error } from '@sveltejs/kit';
import { metaGetMeta } from '$lib/client';
import { FIRST_PAGE, PAGE_PARAM } from '$lib/params';
import { type ApiOptions, unwrap } from '$lib/server/api';

export interface Paging {
	page: number;
	take: number;
}

/**
 * The requested page (`?page=`, default 1) and the page size, both within the API's own limits
 * (`/exhibit/meta`): paging settings belong to the API, not to constants here.
 */
export async function paging(url: URL, api: ApiOptions): Promise<Paging> {
	const meta = unwrap(await metaGetMeta(api));
	const page = Number(url.searchParams.get(PAGE_PARAM) ?? FIRST_PAGE);
	if (!Number.isInteger(page) || page < FIRST_PAGE || page > meta.max_page) {
		error(
			400,
			`Page must be a whole number from ${String(FIRST_PAGE)} to ${String(meta.max_page)}.`
		);
	}
	return { page, take: meta.default_page_take };
}
