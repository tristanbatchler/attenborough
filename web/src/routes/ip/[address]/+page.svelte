<script lang="ts">
	import { resolve } from '$app/paths';
	import ActivityTable from '$lib/components/ActivityTable.svelte';
	import CountryFlag from '$lib/components/CountryFlag.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import WorldMap from '$lib/components/WorldMap.svelte';
	import { formatUtc } from '$lib/format';
	import { countryName, locationPoint, lookups, placeName } from '$lib/geo';
	import { beforeSearch } from '$lib/params';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const location = $derived(data.summary.location);
	const point = $derived(location && locationPoint(location));

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

<section>
	<h2>Where it's from</h2>
	{#if location === null}
		<p>This address hasn't been located.</p>
	{:else}
		{#if point}
			<WorldMap points={[point]} label="World map with {placeName(location)} marked" />
		{/if}
		<figure>
			<table>
				<tbody>
					<tr>
						<th scope="row">Country</th>
						<td>
							{#if location.country_code === null}
								Unknown
							{:else}
								<CountryFlag code={location.country_code} />
								{countryName(location.country_code)}
							{/if}
						</td>
					</tr>
					<tr>
						<th scope="row">City</th>
						<td>{location.city ?? 'Unknown'}</td>
					</tr>
					<tr>
						<th scope="row">Network</th>
						<td>
							{#if location.asn === null}
								Unknown
							{:else}
								{location.as_organisation ?? 'Unknown owner'}
								<small>AS{location.asn}</small>
							{/if}
						</td>
					</tr>
				</tbody>
			</table>
		</figure>
		<p>
			<small>
				An estimate from {location.source}, made
				<time datetime={location.located_at}>{formatUtc(location.located_at)}</time> when the address
				was first seen. It says where the address is registered and routed, not where the sender is: most
				scanners rent servers in data centres, and the city is the data centre's.
			</small>
		</p>
	{/if}
	<nav aria-label="More about this address">
		<ul>
			<li>More about this address:</li>
			{#each lookups(data.address) as lookup (lookup.name)}
				<li><a href={lookup.href} rel="external noreferrer">{lookup.name}</a></li>
			{/each}
		</ul>
	</nav>
</section>

{#if data.events.items.length === 0}
	<p>
		{data.isFirstPage
			? 'No activity has been recorded from this address.'
			: 'There is no more activity for this address.'}
	</p>
{:else}
	<ActivityTable page={data.events} />
{/if}

<Pagination isFirstPage={data.isFirstPage} nextCursor={data.events.next_cursor} href={pageHref} />
