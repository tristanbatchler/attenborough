import type { IncomingMessage } from 'node:http';

// See https://svelte.dev/docs/kit/types#app.d.ts
declare global {
	namespace App {
		// adapter-node passes the Node request, which keeps the request line exactly as sent.
		// Absent in `vite dev`.
		interface Platform {
			req: IncomingMessage;
		}
	}
}

export {};
