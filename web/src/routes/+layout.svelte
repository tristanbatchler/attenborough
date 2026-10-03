<script lang="ts">
	import '../app.scss';
	import { resolve } from '$app/paths';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<header>
	<nav>
		<ul>
			<li><a href={resolve('/')}><strong>Attenborough</strong></a></li>
		</ul>
		<ul>
			<li><a href={resolve('/')}>Exhibit</a></li>
			<li><a href={resolve('/patterns')}>Patterns</a></li>
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
