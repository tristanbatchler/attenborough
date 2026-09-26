import { error } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

// Connection settings for the generated API client (src/lib/client). This file only says
// *where* the API is and *how* to fetch; every endpoint, parameter and type comes from the
// generated SDK. Never hand-write API calls: change the API and run `npm run gen-types`.
//
// Server-only ($lib/server): the API's address is private configuration, and SvelteKit refuses
// to bundle this module for the browser.

export interface ApiOptions {
	baseUrl: string;
	fetch: typeof fetch;
}

/** The API's address. Throws if unset; `init` in hooks.server.ts calls this at startup. */
export function apiBaseUrl(): string {
	const baseUrl = env.API_BASE_URL;
	if (!baseUrl) {
		throw new Error(
			'API_BASE_URL is not set. Copy web/.env.example to web/.env (or set it in the ' +
				'environment); see web/README.md.'
		);
	}
	return baseUrl;
}

/** Options to spread into any generated SDK call made from a server `load` function. */
export function apiOptions(fetch: typeof globalThis.fetch): ApiOptions {
	return { baseUrl: apiBaseUrl(), fetch };
}

/** The part of a generated SDK call's result that says whether it succeeded. */
interface ApiResult<T> {
	data: T | undefined;
	error: unknown;
	response?: Response;
}

const HTTP_UNPROCESSABLE_CONTENT = 422;

/**
 * The data of a generated SDK call, or the matching error page. SDK calls never throw: an
 * unreachable API has no `response` (503), a 422 means the API rejected the request's input
 * (400, with `invalidInput` as the message), and anything else is the API's failure (502).
 */
export function unwrap<T>(result: ApiResult<T>, invalidInput = 'The request was not valid.'): T {
	if (result.data !== undefined) {
		return result.data;
	}
	if (result.response === undefined) {
		console.error('Exhibit API unreachable', result.error);
		error(503, 'The exhibit is temporarily unavailable.');
	}
	if (result.response.status === HTTP_UNPROCESSABLE_CONTENT) {
		error(400, invalidInput);
	}
	console.error('Exhibit API error', result.response.status, result.error);
	error(502, 'The exhibit could not load this page.');
}
