import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	css: {
		preprocessorOptions: {
			scss: {
				// Silence warnings from third-party stylesheets only (Pico 2.1.1 uses Sass's
				// deprecated `if()`); warnings about our own SCSS still show.
				quietDeps: true
			}
		}
	},
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// Self-hosted Node server (`node build`), deployed behind the same reverse proxy as the
			// API. See web/README.md, "Deployment".
			adapter: adapter()
		})
	]
});
