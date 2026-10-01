<script lang="ts">
	import { resolve } from '$app/paths';
	import ActivityTable from '$lib/components/ActivityTable.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import { formatUtc } from '$lib/format';
	import { FIRST_PAGE, PAGE_PARAM } from '$lib/params';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const pageHref = (page: number) =>
		resolve(`/ip/[address]?${PAGE_PARAM}=${String(page)}`, { address: data.address });
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
		{data.page === FIRST_PAGE
			? 'No activity has been recorded from this address.'
			: 'There is no more activity for this address.'}
	</p>
{:else}
	<ActivityTable events={data.events.items} />
{/if}

<Pagination page={data.page} hasNextPage={data.events.has_next} href={pageHref} />
