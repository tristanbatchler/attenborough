<script lang="ts">
	import { resolve } from '$app/paths';
	import ActivityTable from '$lib/components/ActivityTable.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const pageHref = (page: number) =>
		resolve(`/ip/[address]?page=${String(page)}`, { address: data.address });
</script>

<svelte:head>
	<title>{data.address} · Attenborough</title>
</svelte:head>

<hgroup>
	<h1>Activity from <code>{data.address}</code></h1>
	<p>Everything this address did, most recent first. Times are in UTC.</p>
</hgroup>

{#if data.rows.length === 0}
	<p>
		{data.page === 1
			? 'No activity has been recorded from this address.'
			: 'There is no more activity for this address.'}
	</p>
{:else}
	<ActivityTable rows={data.rows} />
{/if}

<Pagination page={data.page} hasNextPage={data.hasNextPage} href={pageHref} />
