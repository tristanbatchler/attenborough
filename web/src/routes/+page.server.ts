import { constants } from 'node:http2';
import { listRecentEvents, listSearchFields, type HttpValidationError } from '$lib/client';
import { SEARCH_PARAM } from '$lib/params';
import { apiOptions, unwrap } from '$lib/server/api';
import { requestedCursor } from '$lib/server/paging';
import type { PageServerLoad } from './$types';

/** Why the API refused the search, if that is why it refused the request (search.py says why). */
function searchProblem(error: HttpValidationError | undefined): string | undefined {
	return error?.detail?.find(({ loc }) => loc.includes(SEARCH_PARAM))?.msg;
}

export const load: PageServerLoad = async ({ url, fetch }) => {
	const before = requestedCursor(url);
	const q = url.searchParams.get(SEARCH_PARAM)?.trim() ?? '';
	const [result, fields] = await Promise.all([
		listRecentEvents({ ...apiOptions(fetch), query: { before, q } }),
		listSearchFields(apiOptions(fetch))
	]);
	const problem =
		result.response?.status === constants.HTTP_STATUS_UNPROCESSABLE_ENTITY
			? searchProblem(result.error)
			: undefined;
	return {
		q,
		problem,
		fields: unwrap(fields),
		isFirstPage: before === undefined,
		events: problem === undefined ? unwrap(result, 'That page does not exist.') : undefined
	};
};
