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
