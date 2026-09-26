<script lang="ts">
	import type { ResolvedPathname } from '$app/types';

	// `href` must return a resolve()d path: the type makes callers resolve their links, and lets
	// svelte/no-navigation-without-resolve accept the links below.
	let {
		page,
		hasNextPage,
		href
	}: { page: number; hasNextPage: boolean; href: (page: number) => ResolvedPathname } = $props();
</script>

{#if page > 1 || hasNextPage}
	<nav aria-label="Pages">
		<ul>
			{#if page > 1}
				<li><a href={href(page - 1)} rel="prev">← Newer</a></li>
			{/if}
		</ul>
		<ul>
			{#if hasNextPage}
				<li><a href={href(page + 1)} rel="next">Older →</a></li>
			{/if}
		</ul>
	</nav>
{/if}
