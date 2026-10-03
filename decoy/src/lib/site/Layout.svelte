<script lang="ts">
	import { resolve } from '$app/paths';
	import type { Snippet } from 'svelte';
	import {
		AUTHORS,
		FAN_NOTICE,
		SITE_DESCRIPTION,
		SITE_NAME,
		TAGLINE,
		WORDPRESS_VERSION,
		authorPath
	} from './blog';

	// Every blog page's frame, modelled on a classic WordPress theme. Rendered by $lib/server/html:
	// the CSS is a plain style element in the head, never a component style block.
	let { title, children }: { title: string; children: Snippet } = $props();
</script>

<svelte:head>
	<meta charset="UTF-8" />
	<meta name="viewport" content="width=device-width, initial-scale=1" />
	<title>{title}</title>
	<meta name="description" content={SITE_DESCRIPTION} />
	<meta name="generator" content="WordPress {WORDPRESS_VERSION}" />
	<link rel="alternate" type="application/rss+xml" title="{SITE_NAME} &raquo; Feed" href="/feed/" />
	<link rel="https://api.w.org/" href="/wp-json/" />
	<link rel="EditURI" type="application/rsd+xml" title="RSD" href="/xmlrpc.php?rsd" />
	<style>
		body {
			margin: 0;
			background: #f6f1ea;
			color: #2b2118;
			font-family: Georgia, 'Times New Roman', serif;
			font-size: 18px;
			line-height: 1.6;
		}
		a {
			color: #8c1c13;
		}
		.site-header,
		.site-main,
		.site-footer {
			max-width: 760px;
			margin: 0 auto;
			padding: 24px;
		}
		.site-header {
			border-bottom: 3px double #8c1c13;
		}
		.site-title {
			margin: 0;
			font-size: 2.2em;
			letter-spacing: 0.02em;
		}
		.site-title a {
			color: inherit;
			text-decoration: none;
		}
		.site-description {
			margin: 4px 0 0;
			font-style: italic;
			color: #6b5a4a;
		}
		.main-navigation ul {
			margin: 12px 0 0;
			padding: 0;
			list-style: none;
			display: flex;
			gap: 18px;
			font-family: Helvetica, Arial, sans-serif;
			font-size: 0.8em;
			text-transform: uppercase;
		}
		.entry-title {
			margin-bottom: 4px;
		}
		.entry-meta {
			font-family: Helvetica, Arial, sans-serif;
			font-size: 0.75em;
			color: #6b5a4a;
		}
		.site-footer {
			border-top: 1px solid #d9cbb8;
			font-family: Helvetica, Arial, sans-serif;
			font-size: 0.75em;
			color: #6b5a4a;
		}
	</style>
</svelte:head>

<div id="page" class="site">
	<header id="masthead" class="site-header">
		<p class="site-title"><a href={resolve('/')} rel="home">{SITE_NAME}</a></p>
		<p class="site-description">{TAGLINE}</p>
		<nav id="site-navigation" class="main-navigation" aria-label="Primary Menu">
			<ul id="primary-menu" class="menu">
				<li class="menu-item"><a href={resolve('/')}>Home</a></li>
				{#each AUTHORS as author (author.id)}
					<li class="menu-item"><a href={authorPath(author)}>{author.name}</a></li>
				{/each}
				<li class="menu-item"><a href={resolve('/feed')}>RSS</a></li>
			</ul>
		</nav>
	</header>

	<main id="primary" class="site-main">
		{@render children()}
	</main>

	<footer id="colophon" class="site-footer">
		<p>{FAN_NOTICE}</p>
		<p><a href="https://wordpress.org/">Proudly powered by WordPress</a></p>
	</footer>
</div>
