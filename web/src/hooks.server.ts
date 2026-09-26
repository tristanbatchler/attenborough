import type { ServerInit } from '@sveltejs/kit';
import { apiBaseUrl } from '$lib/server/api';

// Fail at startup, not on the first page that needs the API.
export const init: ServerInit = () => {
	apiBaseUrl();
};
