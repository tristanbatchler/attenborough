<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
</script>

<svelte:head>
	<title>{page.status} · Attenborough</title>
</svelte:head>

<hgroup>
	<h1>{page.status}</h1>
	<p>{page.error?.message}</p>
</hgroup>

<p><a href={resolve('/')}>Back to the exhibit</a></p>
