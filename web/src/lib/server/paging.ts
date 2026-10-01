import { BEFORE_PARAM } from '$lib/params';

/**
 * Where the requested page starts (`?before=`), or undefined for the first, newest page. The token
 * is the API's own and passed back unread: the API rejects one it didn't make (422, which `unwrap`
 * turns into a 400).
 */
export function requestedCursor(url: URL): string | undefined {
	return url.searchParams.get(BEFORE_PARAM) ?? undefined;
}
