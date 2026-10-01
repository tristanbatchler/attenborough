<script lang="ts">
	import { resolve } from '$app/paths';
	import ActivityTable from '$lib/components/ActivityTable.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import { formatUtc } from '$lib/format';
	import { beforeSearch } from '$lib/params';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const pageHref = (before?: string) =>
		before === undefined
			? resolve('/ip/[address]', { address: data.address })
			: resolve(`/ip/[address]?${beforeSearch(before)}`, { address: data.address });
</script>

<svelte:head>
	<title>{data.address} · Attenborough</title>
</svelte:head>

<hgroup>
	<h1>Activity from <code>{data.address}</code></h1>
	<p>Everything this address did, most recent first. Times are in UTC.</p>
</hgroup>

{#if data.summary.first_seen_at !== null && data.summary.last_seen_at !== null}
	<figure>
		<table>
			<tbody>
				<tr><th scope="row">Requests</th><td>{data.summary.requests}</td></tr>
				<tr><th scope="row">Distinct paths</th><td>{data.summary.distinct_paths}</td></tr>
				<tr><th scope="row">Login attempts</th><td>{data.summary.login_attempts}</td></tr>
				<tr>
					<th scope="row">First seen</th>
					<td>
						<time datetime={data.summary.first_seen_at}>
							{formatUtc(data.summary.first_seen_at)}
						</time>
					</td>
				</tr>
				<tr>
					<th scope="row">Last seen</th>
					<td>
						<time datetime={data.summary.last_seen_at}>
							{formatUtc(data.summary.last_seen_at)}
						</time>
					</td>
				</tr>
			</tbody>
		</table>
	</figure>
{/if}

{#if data.events.items.length === 0}
	<p>
		{data.isFirstPage
			? 'No activity has been recorded from this address.'
			: 'There is no more activity for this address.'}
	</p>
{:else}
	<ActivityTable events={data.events.items} />
{/if}

<Pagination isFirstPage={data.isFirstPage} nextCursor={data.events.next_cursor} href={pageHref} />
