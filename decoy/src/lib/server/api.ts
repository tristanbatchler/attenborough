import type { RequestEvent } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

// Connection settings for the generated API client (src/lib/client). Every endpoint, parameter
// and type comes from the generated SDK. Never hand-write API calls: change the API and run
// `npm run gen-types`.
//
// Server-only ($lib/server): the API's address is private configuration.

// The API attributes each report to the visitor named here. It counts only because this server's
// address is in the API's FORWARDED_ALLOW_IPS (api/README.md, "Client IP attribution").
const FORWARDED_FOR_HEADER = 'x-forwarded-for';

/** The API's address. Throws if unset; `init` in hooks.server.ts calls this at startup. */
export function apiBaseUrl(): string {
	const baseUrl = env.API_BASE_URL;
	if (!baseUrl) {
		throw new Error(
			'API_BASE_URL is not set. Copy decoy/.env.example to decoy/.env (or set it in the ' +
				'environment); see decoy/README.md.'
		);
	}
	return baseUrl;
}

/**
 * Options to spread into any generated SDK call made while serving `event`: the API's address,
 * and the visitor the call is about. X-Forwarded-For is set here, to the one address SvelteKit
 * attributed the request to, so any X-Forwarded-For the visitor sent never reaches the API.
 *
 * The client uses the global fetch, not SvelteKit's `event.fetch`, which would pass the visitor's
 * cookies on to the API.
 */
export function apiOptions(event: RequestEvent) {
	return {
		baseUrl: apiBaseUrl(),
		headers: { [FORWARDED_FOR_HEADER]: event.getClientAddress() }
	};
}
