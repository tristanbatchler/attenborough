<script lang="ts">
	import { resolve } from '$app/paths';
	import { formatUtc } from '$lib/format';
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
	<figure>
		<table>
			<thead>
				<tr>
					<th scope="col">When</th>
					<th scope="col">Event</th>
					<th scope="col">Target</th>
					<th scope="col">Details</th>
				</tr>
			</thead>
			<tbody>
				{#each data.rows as row, index (index)}
					<tr>
						<td><time datetime={row.event_at}>{formatUtc(row.event_at)}</time></td>
						<td>{row.event_type}</td>
						<td><code>{row.target_slug}</code></td>
						<td><code>{row.details}</code></td>
					</tr>
				{/each}
			</tbody>
		</table>
	</figure>
{/if}

{#if data.page > 1 || data.hasNextPage}
	<nav aria-label="Pages">
		<ul>
			{#if data.page > 1}
				<li>
					<a href={pageHref(data.page - 1)} rel="prev">← Newer</a>
				</li>
			{/if}
		</ul>
		<ul>
			{#if data.hasNextPage}
				<li>
					<a href={pageHref(data.page + 1)} rel="next">Older →</a>
				</li>
			{/if}
		</ul>
	</nav>
{/if}
