<script lang="ts">
	import '../app.scss';
	import { resolve } from '$app/paths';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();
</script>

<header>
	<nav>
		<ul>
			<li><a href={resolve('/')}><strong>Attenborough</strong></a></li>
		</ul>
		<ul>
			<li><a href={resolve('/')}>Exhibit</a></li>
			<li><a href={resolve('/patterns')}>Patterns</a></li>
			{#if data.admin}
				<li><a href={resolve('/admin')}>Admin</a></li>
			{:else}
				<!-- A server endpoint (off to Google), so a full page load, not client-side routing. -->
				<li><a href={resolve('/auth/google')} data-sveltekit-reload>Log in</a></li>
			{/if}
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
	<!-- Required by the geolocation databases' licence (CC BY 4.0). -->
	<small><a href="https://db-ip.com" rel="external">IP geolocation by DB-IP</a></small>
</footer>
