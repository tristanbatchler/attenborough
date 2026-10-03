import type { Handle, RequestEvent, ServerInit } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { setTimeout as sleep } from 'node:timers/promises';
import { judgeVisit, reportHit, type RenderedResponse, type VisitVerdict } from '$lib/client';
import { apiBaseUrl, apiOptions } from '$lib/server/api';
import { CONTENT_TYPE_HEADER } from '$lib/server/headers';
import { nginxError } from '$lib/server/nginx';
import { captureVisit, type Visit } from '$lib/server/visit';

// How long a visitor's response may wait for each call to the API: the verdict, then the report.
// The API answers the verdict with a few indexed lookups, and the report before writing
// (/ingest/hits records in the background), so this is only ever reached if the API is down.
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
// The verdict when the API can't give one: serve the decoy's own page.
const SERVE_AS_USUAL: VisitVerdict = { banned: false, rule_id: null, response: null };

/**
 * How to answer the visit: refuse it (banned), serve a response rule's answer, or serve the decoy's
 * own page. If the API can't say, the visitor is served as usual: an API that is down never
 * changes a visitor's response.
 */
async function judge(event: RequestEvent, visit: Visit): Promise<VisitVerdict> {
	const result = await judgeVisit({
		...apiOptions(event),
		body: { method: visit.method, path: visit.path, query: visit.query, headers: visit.headers },
		signal: AbortSignal.timeout(API_TIMEOUT_MS)
	});
	if (result.data === undefined) {
		console.error('Failed to ask how to answer a visit', result.error);
		return SERVE_AS_USUAL;
	}
	return result.data;
}

/** A response rule's answer, as the API rendered it, after the delay it asks for. */
async function ruleResponse(rendered: RenderedResponse): Promise<Response> {
	await sleep(rendered.delay_ms);
	const headers = new Headers(rendered.headers);
	headers.set(CONTENT_TYPE_HEADER, rendered.content_type);
	// The API allows no body for statuses that can't have one (204, 205, 304).
	return new Response(rendered.body === '' ? null : rendered.body, {
		status: rendered.status_code,
		headers
	});
}

/**
 * Report one served request to the API, which records it as a honeypot hit. A failure is logged
 * and never changes the visitor's response.
 */
async function reportVisit(
	event: RequestEvent,
	visit: Visit,
	status: number,
	verdict: VisitVerdict
): Promise<void> {
	const result = await reportHit({
		...apiOptions(event),
		body: {
			...visit,
			body: visit.body && Buffer.from(visit.body).toString('base64'),
			status_code: status,
			banned: verdict.banned,
			rule_id: verdict.rule_id
		},
		signal: AbortSignal.timeout(API_TIMEOUT_MS)
	});
	if (result.response?.ok !== true) {
		console.error('Failed to report a decoy hit', visit.path, result.error);
	}
}

// Every request the decoy serves, 404s included, is reported exactly once, with what the visitor
// sent and the status they got. A banned visitor gets nginx's 403 for everything, and a request a
// response rule matches gets the rule's answer (api/src/attenborough/rules.py); both are reported
// too. The report is awaited, not left floating, so none is lost when the server stops.
export const handle: Handle = async ({ event, resolve }) => {
	const visit = await captureVisit(event);
	const verdict = await judge(event, visit);
	let response: Response;
	if (verdict.banned) {
		response = nginxError(constants.HTTP_STATUS_FORBIDDEN);
	} else if (verdict.response !== null) {
		response = await ruleResponse(verdict.response);
	} else if (visit.path.endsWith(SVELTEKIT_DATA_SUFFIX)) {
		response = nginxError(constants.HTTP_STATUS_NOT_FOUND);
	} else {
		response = await resolve(event);
	}
	await reportVisit(event, visit, response.status, verdict);
	return response;
};
