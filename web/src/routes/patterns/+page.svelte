<script lang="ts">
	import { resolve } from '$app/paths';
	import { CATEGORIES } from '$lib/categories';
	import AddressTable from '$lib/components/AddressTable.svelte';
	import CountryFlag from '$lib/components/CountryFlag.svelte';
	import Heatmap from '$lib/components/Heatmap.svelte';
	import RankTable from '$lib/components/RankTable.svelte';
	import WorldMap from '$lib/components/WorldMap.svelte';
	import { formatCount, formatUtc } from '$lib/format';
	import { countryName, placeName } from '$lib/geo';
	import type {
		CategoryCount,
		CountryCount,
		CredentialCount,
		NetworkCount,
		PathCount,
		UserAgentCount
	} from '$lib/client';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const patterns = $derived(data.patterns);
	const totals = $derived(patterns.totals);

	const points = $derived(
		patterns.places.map((place) => ({
			latitude: place.latitude,
			longitude: place.longitude,
			weight: place.requests,
			title: `${placeName(place) || 'Unknown place'}: ${formatCount(place.requests)} requests from ${formatCount(place.addresses)} addresses`
		}))
	);
	const requests = (row: { requests: number }) => row.requests;
	const attempts = (row: { attempts: number }) => row.attempts;
</script>

<svelte:head>
	<title>Patterns · Attenborough</title>
</svelte:head>

<hgroup>
	<h1>Patterns</h1>
	<p>What the honeypot's visitors are after, who they are, when they come, and what they bring.</p>
</hgroup>

<p>
	<small>
		Worked out from everything recorded, at most every few minutes; last at
		<time datetime={patterns.computed_at}>{formatUtc(patterns.computed_at)}</time>. Sections marked
		<em>this week</em> count from
		<time datetime={patterns.window_start}>{formatUtc(patterns.window_start)}</time>; the rest cover
		all time.
	</small>
</p>

<section>
	<h2>At a glance</h2>
	<figure>
		<table>
			<tbody>
				<tr><th scope="row">Requests</th><td>{formatCount(totals.requests)}</td></tr>
				<tr
					><th scope="row">In the last 24 hours</th><td>{formatCount(totals.requests_last_day)}</td
					></tr
				>
				<tr><th scope="row">Login attempts</th><td>{formatCount(totals.login_attempts)}</td></tr>
				<tr
					><th scope="row">WordPress installs</th><td>{formatCount(totals.install_attempts)}</td
					></tr
				>
				<tr><th scope="row">Addresses</th><td>{formatCount(totals.addresses)}</td></tr>
				<tr><th scope="row">Countries</th><td>{formatCount(totals.countries)}</td></tr>
				{#if totals.first_seen_at !== null && totals.last_seen_at !== null}
					<tr>
						<th scope="row">Watching since</th>
						<td><time datetime={totals.first_seen_at}>{formatUtc(totals.first_seen_at)}</time></td>
					</tr>
					<tr>
						<th scope="row">Latest request</th>
						<td><time datetime={totals.last_seen_at}>{formatUtc(totals.last_seen_at)}</time></td>
					</tr>
				{/if}
			</tbody>
		</table>
	</figure>
</section>

<section>
	<h2>Where they are</h2>
	{#if points.length === 0}
		<p>No address has been located yet.</p>
	{:else}
		<WorldMap {points} label="World map of where the honeypot's visitors are" />
	{/if}
	<p>
		<small>
			Each point is a place visitors' addresses are registered, sized by requests. Locations are
			estimates from DB-IP, not proof of where anyone is: most scanners rent servers in data
			centres.
		</small>
	</p>
	<h3>Countries</h3>
	<RankTable
		rows={patterns.countries}
		heading="Country"
		countHeading="Requests"
		count={requests}
		empty="Nothing recorded yet."
	>
		{#snippet name(row: CountryCount)}
			{#if row.country_code === null}
				Unknown
			{:else}
				<CountryFlag code={row.country_code} />
				{countryName(row.country_code)}
			{/if}
		{/snippet}
	</RankTable>
	<h3>Networks</h3>
	<p>Who runs the networks the addresses belong to: mostly hosting and cloud companies.</p>
	<RankTable
		rows={patterns.networks}
		heading="Network"
		countHeading="Requests"
		count={requests}
		empty="Nothing recorded yet."
	>
		{#snippet name(row: NetworkCount)}
			{#if row.asn === null}
				Unknown
			{:else}
				{row.as_organisation ?? 'Unknown owner'}
				<small>AS{row.asn}</small>
			{/if}
		{/snippet}
	</RankTable>
</section>

<section>
	<h2>What they're after <small>this week</small></h2>
	<p>Each request's path, sorted by what it looks for. A guess from the path alone.</p>
	<RankTable
		rows={patterns.categories}
		heading="Looking for"
		countHeading="Requests"
		count={requests}
		empty="No requests this week."
	>
		{#snippet name(row: CategoryCount)}
			{CATEGORIES[row.category].label}
			<small>{CATEGORIES[row.category].description}</small>
		{/snippet}
	</RankTable>
	<h3>Most requested paths</h3>
	<RankTable
		rows={patterns.paths}
		heading="Path"
		countHeading="Requests"
		count={requests}
		empty="No requests this week."
	>
		{#snippet name(row: PathCount)}
			<code>{row.path}</code>
			<small>{CATEGORIES[row.category].label}</small>
		{/snippet}
	</RankTable>
</section>

<section>
	<h2>When they come <small>this week</small></h2>
	<p>Requests per hour, in UTC. Darker is busier.</p>
	<Heatmap days={patterns.days} />
</section>

<section>
	<h2>Their wordlists <small>this week</small></h2>
	<p>The usernames and passwords tried most on the decoy's login pages.</p>
	<RankTable
		rows={patterns.usernames}
		heading="Username"
		countHeading="Attempts"
		count={attempts}
		empty="No login attempts this week."
	>
		{#snippet name(row: CredentialCount)}<code>{row.value}</code>{/snippet}
	</RankTable>
	<RankTable
		rows={patterns.passwords}
		heading="Password"
		countHeading="Attempts"
		count={attempts}
		empty="No login attempts this week."
	>
		{#snippet name(row: CredentialCount)}<code>{row.value}</code>{/snippet}
	</RankTable>
</section>

<section>
	<h2>Their tools</h2>
	<h3>User agents <small>this week</small></h3>
	<p>What each request said it was. Anyone can claim to be a browser, and most do.</p>
	<RankTable
		rows={patterns.user_agents}
		heading="User agent"
		countHeading="Requests"
		count={requests}
		empty="No requests this week."
	>
		{#snippet name(row: UserAgentCount)}
			{#if row.user_agent === null}
				<em>None sent</em>
			{:else}
				<code>{row.user_agent}</code>
			{/if}
		{/snippet}
	</RankTable>
	<h3>One toolkit, many addresses</h3>
	<p>
		Addresses that each requested exactly the same set of paths: the same tool, run from several
		machines.
	</p>
	{#each patterns.toolkits as toolkit, index (index)}
		<article>
			<header>
				{formatCount(toolkit.address_count)} addresses, the same {formatCount(toolkit.paths)} paths
			</header>
			<ul>
				{#each toolkit.example_paths as path (path)}
					<li><code>{path}</code></li>
				{/each}
				{#if toolkit.paths > toolkit.example_paths.length}<li>…</li>{/if}
			</ul>
			<footer>
				<ul>
					{#each toolkit.addresses as address (address)}
						<li><a href={resolve('/ip/[address]', { address })}><code>{address}</code></a></li>
					{/each}
					{#if toolkit.address_count > toolkit.addresses.length}<li>…</li>{/if}
				</ul>
			</footer>
		</article>
	{:else}
		<p>None yet.</p>
	{/each}
</section>

<section>
	<h2>The regulars</h2>
	<h3>Busiest</h3>
	<AddressTable rows={patterns.busiest} />
	<h3>Seen over the longest time</h3>
	<AddressTable rows={patterns.longest_seen} />
</section>
