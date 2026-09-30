import { error } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { FIRST_PAGE, PAGE_PARAM } from '$lib/params';

/**
 * The requested page (`?page=`, default 1). Only its form is checked here; the API owns the page
 * limits and rejects a page past them (422, which `unwrap` turns into a 400).
 */
export function requestedPage(url: URL): number {
	const page = Number(url.searchParams.get(PAGE_PARAM) ?? FIRST_PAGE);
	if (!Number.isInteger(page) || page < FIRST_PAGE) {
		error(
			constants.HTTP_STATUS_BAD_REQUEST,
			`Page must be a whole number from ${String(FIRST_PAGE)}.`
		);
	}
	return page;
}
