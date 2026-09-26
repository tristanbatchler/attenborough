import { defineConfig } from '@hey-api/openapi-ts';

// Generates the typed API client in src/lib/client from the FastAPI spec. Never hand-write API
// calls: change the API, then run `npm run gen-types`. The spec is written by the API on
// every startup (api/src/openapi.json).
export default defineConfig({
	input: '../api/src/openapi.json',
	output: 'src/lib/client',
	parser: {
		filters: {
			operations: {
				// Only the public exhibit. The honeypot's decoy routes share the spec but are for
				// scanners, not the frontend.
				include: ['/^[A-Z]+ \\/exhibit\\//'],
				// Every router's debug /test route.
				exclude: ['/^[A-Z]+ .*\\/test$/']
			}
		}
	},
	plugins: ['@hey-api/client-fetch', '@hey-api/typescript', '@hey-api/sdk']
});
