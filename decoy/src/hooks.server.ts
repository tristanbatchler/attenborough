import type { Handle, RequestEvent, ServerInit } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { judgeVisit, reportHit } from '$lib/client';
import { apiBaseUrl, apiOptions } from '$lib/server/api';
import { nginxError } from '$lib/server/nginx';
import { captureVisit, type Visit } from '$lib/server/visit';

// How long a visitor's response may wait for each call to the API: the verdict, then the report.
// The API answers the verdict with one indexed lookup, and the report before writing (/ingest/hits
// records in the background), so this is only ever reached if the API is down.
const API_TIMEOUT_MS = 2000;

// SvelteKit answers `<path>/__data.json` itself, with its own JSON, for every route: a giveaway. It
// also strips the suffix from `event.url` before this hook runs, so check the raw path.
const SVELTEKIT_DATA_SUFFIX = '__data.json';

// Fail at startup, not on the first request that needs the API.
export const init: ServerInit = () => {
	apiBaseUrl();
};

/**
 * Whether the API has banned the visitor. If it can't say, the visitor is served as usual: an API
 * that is down never changes a visitor's response.
 */
async function isBanned(event: RequestEvent): Promise<boolean> {
	const result = await judgeVisit({
		...apiOptions(event),
		signal: AbortSignal.timeout(API_TIMEOUT_MS)
	});
	if (result.data === undefined) {
		console.error('Failed to ask whether a visitor is banned', result.error);
		return false;
	}
	return result.data.banned;
}

/**
 * Report one served request to the API, which records it as a honeypot hit. A failure is logged
 * and never changes the visitor's response.
 */
async function reportVisit(
	event: RequestEvent,
	visit: Visit,
	status: number,
	banned: boolean
): Promise<void> {
	const result = await reportHit({
		...apiOptions(event),
		body: {
			...visit,
			body: visit.body && Buffer.from(visit.body).toString('base64'),
			status_code: status,
			banned
		},
		signal: AbortSignal.timeout(API_TIMEOUT_MS)
	});
	if (result.response?.ok !== true) {
		console.error('Failed to report a decoy hit', visit.path, result.error);
	}
}

// Every request the decoy serves, 404s included, is reported exactly once, with what the visitor
// sent and the status they got. A banned visitor gets nginx's 403 for everything, and is still
// reported. The report is awaited, not left floating, so none is lost when the server stops.
export const handle: Handle = async ({ event, resolve }) => {
	const visit = await captureVisit(event);
	const banned = await isBanned(event);
	let response: Response;
	if (banned) {
		response = nginxError(constants.HTTP_STATUS_FORBIDDEN);
	} else if (visit.path.endsWith(SVELTEKIT_DATA_SUFFIX)) {
		response = nginxError(constants.HTTP_STATUS_NOT_FOUND);
	} else {
		response = await resolve(event);
	}
	await reportVisit(event, visit, response.status, banned);
	return response;
};
