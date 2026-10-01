<script lang="ts">
	import type { ResolvedPathname } from '$app/types';

	// Pages are keyset pages: each starts after the API's `next_cursor` from the one before, so a
	// listing only goes older, or back to the newest page. `href` must return a resolve()d path:
	// the type makes callers resolve their links, and lets svelte/no-navigation-without-resolve
	// accept the links below.
	let {
		isFirstPage,
		nextCursor,
		href
	}: {
		isFirstPage: boolean;
		nextCursor: string | null;
		href: (before?: string) => ResolvedPathname;
	} = $props();
</script>

{#if !isFirstPage || nextCursor !== null}
	<nav aria-label="Pages">
		<ul>
			{#if !isFirstPage}
				<li><a href={href()}>← Newest</a></li>
			{/if}
		</ul>
		<ul>
			{#if nextCursor !== null}
				<li><a href={href(nextCursor)} rel="next">Older →</a></li>
			{/if}
		</ul>
	</nav>
{/if}
