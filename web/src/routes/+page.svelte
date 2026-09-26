<script lang="ts">
	import { resolve } from '$app/paths';
	import ActivityTable from '$lib/components/ActivityTable.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const pageHref = (page: number) => resolve(`/?page=${String(page)}`);
</script>

<svelte:head>
	<title>Attenborough</title>
</svelte:head>

<hgroup>
	<h1>Attenborough</h1>
	<p>Field observations of the internet's automated visitors.</p>
</hgroup>

<p>
	Attenborough presents decoy resources to scanners and bots, and records what they do: the paths
	they probe, the credentials they try, and the decoys they take. This exhibit shows those
	observations in full.
</p>

<section>
	<h2>Look up an address</h2>
	<form method="GET" action={resolve('/ip')}>
		<label>
			IP address
			<input name="address" type="text" placeholder="203.0.113.7" autocomplete="off" required />
		</label>
		<button type="submit">View activity</button>
	</form>
</section>

<section>
	<h2>Latest activity</h2>
	<p>The most recent attempts from every address, newest first. Times are in UTC.</p>
	{#if data.rows.length === 0}
		<p>
			{data.page === 1 ? 'Nothing has been recorded yet.' : 'There is no older activity.'}
		</p>
	{:else}
		<ActivityTable rows={data.rows} />
	{/if}
	<Pagination page={data.page} hasNextPage={data.hasNextPage} href={pageHref} />
</section>
