import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// `npm run dev` port, next to the exhibit's (web/, Vite's default 5173).
const DEV_PORT = 5174;

export default defineConfig({
	server: { port: DEV_PORT, strictPort: true },
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// SvelteKit rejects form posts whose Origin header doesn't match the site, and bots
			// posting to a login form rarely send one: a 403 there would give the decoy away. There
			// are no real sessions here to protect, so accept form posts from anywhere.
			csrf: { trustedOrigins: ['*'] },

			// SvelteKit answers every request under its app directory (default `_app`) itself, before
			// the handle hook, so a probe for `/_app/...` would get SvelteKit's reply and never be
			// reported. Nothing links to this directory (there's no client build), so a name no one
			// will guess sends every such probe through the hook to an nginx 404 instead.
			appDir: 'c3f9a1e7',

			// Self-hosted Node server (`node build`) behind the public reverse proxy. See
			// decoy/README.md, "Deployment".
			adapter: adapter()
		})
	]
});
