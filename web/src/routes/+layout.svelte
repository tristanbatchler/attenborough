<script lang="ts">
	import '../app.scss';
	import { resolve } from '$app/paths';
	import favicon from '$lib/assets/favicon.svg';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<header>
	<nav>
		<ul>
			<li><a href={resolve('/')}><strong>Attenborough</strong></a></li>
		</ul>
		<ul>
			<li><a href={resolve('/')}>Exhibit</a></li>
		</ul>
	</nav>
</header>

<main>
	{@render children()}
</main>

<footer>
	<small>
		Attenborough is a honeypot. Everything shown here was sent to it by scanners and bots, and is
		displayed exactly as received.
	</small>
</footer>
