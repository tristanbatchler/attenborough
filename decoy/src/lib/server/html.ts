import type { Component } from 'svelte';
import { render } from 'svelte/server';
import { CONTENT_TYPE_HEADER } from '$lib/server/headers';

// Svelte's hydration markers: blocks (`<!--[-->`, `<!--]-->`, `<!--[-1-->`), empty anchors
// (`<!---->`) and <svelte:head> hashes (`<!--19tzqmq-->`). They exist only for client-side
// hydration, which decoys never use, and they would give the decoy away. Our own comments never
// reach the output: the Svelte compiler drops them.
const HYDRATION_MARKERS = /<!--(?:\[-?\d*|\]|[a-z0-9]*)-->/g;

export interface PageOptions {
	status?: number;
	headers?: Record<string, string>;
	/** The `<body>` element's class, as the imitated software writes it. */
	bodyClass?: string;
}

/**
 * A complete HTML response rendered from a Svelte component, with nothing that reveals Svelte:
 * the component's `<svelte:head>` becomes the head, and the markers are stripped. Components must
 * put their CSS in a plain `<style>` inside `<svelte:head>`: a component `<style>` would add
 * `svelte-*` classes to the markup.
 */
export function htmlPage<Props extends Record<string, unknown>>(
	component: Component<Props>,
	props: Props,
	{ status, headers, bodyClass = '' }: PageOptions = {}
): Response {
	const { head, body } = render(component, { props });
	const html =
		'<!DOCTYPE html>\n<html lang="en-US">\n<head>\n' +
		head +
		`\n</head>\n<body class="${bodyClass}">\n` +
		body +
		'\n</body>\n</html>\n';
	return new Response(html.replace(HYDRATION_MARKERS, ''), {
		status,
		headers: { [CONTENT_TYPE_HEADER]: 'text/html; charset=UTF-8', ...headers }
	});
}
