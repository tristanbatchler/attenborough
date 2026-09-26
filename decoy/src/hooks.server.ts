import type { Handle, RequestEvent, ServerInit } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { hitsRecordDecoyHit } from '$lib/client';
import { apiBaseUrl, apiOptions } from '$lib/server/api';
import { nginxError } from '$lib/server/nginx';
import { captureVisit, type Visit } from '$lib/server/visit';

// How long a visitor's response may wait for its report. The API answers before writing
// (/ingest/hits records in the background), so this is only ever reached if the API is down.
const REPORT_TIMEOUT_MS = 2000;

// SvelteKit answers `<path>/__data.json` itself, with its own JSON, for every route: a giveaway. It
// also strips the suffix from `event.url` before this hook runs, so check the raw path.
const SVELTEKIT_DATA_SUFFIX = '__data.json';

// Fail at startup, not on the first request that needs the API.
export const init: ServerInit = () => {
	apiBaseUrl();
};

/**
 * Report one served request to the API, which records it as a honeypot hit. A failure is logged
 * and never changes the visitor's response.
 */
async function reportHit(event: RequestEvent, visit: Visit, status: number): Promise<void> {
	const result = await hitsRecordDecoyHit({
		...apiOptions(event),
		body: {
			...visit,
			body: visit.body && Buffer.from(visit.body).toString('base64'),
			status_code: status
		},
		signal: AbortSignal.timeout(REPORT_TIMEOUT_MS)
	});
	if (result.response?.ok !== true) {
		console.error('Failed to report a decoy hit', visit.path, result.error);
	}
}

// Every request the decoy serves, 404s included, is reported exactly once, with what the visitor
// sent and the status they got. The report is awaited, not left floating, so none is lost when the
// server stops.
export const handle: Handle = async ({ event, resolve }) => {
	const visit = await captureVisit(event);
	const response = visit.path.endsWith(SVELTEKIT_DATA_SUFFIX)
		? nginxError(constants.HTTP_STATUS_NOT_FOUND)
		: await resolve(event);
	await reportHit(event, visit, response.status);
	return response;
};
