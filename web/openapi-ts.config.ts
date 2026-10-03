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
				// The public exhibit, and the admin area with its login. The decoy's ingest routes share
				// the spec but are the decoy app's.
				include: ['/^[A-Z]+ \\/(exhibit|auth|admin)\\//']
			}
		}
	},
	plugins: ['@hey-api/client-fetch', '@hey-api/typescript', '@hey-api/sdk']
});
