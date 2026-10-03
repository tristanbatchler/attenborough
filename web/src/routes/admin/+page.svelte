<script lang="ts">
	import { resolve } from '$app/paths';
	import BanTable from '$lib/components/BanTable.svelte';
	import { ADDRESS_PARAM } from '$lib/params';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head>
	<title>Admin · Attenborough</title>
</svelte:head>

<hgroup>
	<h1>Bans</h1>
	<p>
		A banned address gets nginx's 403 from the decoy for every request, and each one is still
		recorded. The exhibit shows that it is banned and since when, never why or by whom. Times are in
		UTC.
	</p>
</hgroup>

<section>
	<h2>Ban or unban an address</h2>
	<form method="GET" action={resolve('/admin/ip')}>
		<label>
			IP address
			<input
				name={ADDRESS_PARAM}
				type="text"
				placeholder="203.0.113.7"
				autocomplete="off"
				required
			/>
		</label>
		<button type="submit">Open</button>
	</form>
</section>

<section>
	<h2>Active bans</h2>
	{#if data.bans.length === 0}
		<p>No address is banned.</p>
	{:else}
		<BanTable bans={data.bans} />
	{/if}
</section>
