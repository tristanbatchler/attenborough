<script lang="ts">
	import { resolve } from '$app/paths';
	import ActivityTable from '$lib/components/ActivityTable.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import SearchBox from '$lib/components/SearchBox.svelte';
	import { BEFORE_PARAM, SEARCH_PARAM, searchString } from '$lib/params';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const PROBLEM_ID = 'search-problem';

	const pageHref = (before?: string) => {
		const search = searchString({ [SEARCH_PARAM]: data.q, [BEFORE_PARAM]: before });
		return resolve(search ? `/?${search}` : '/');
	};
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
	<h2>Search</h2>
	<form method="GET" action={resolve('/')}>
		<!-- Rebuilt for each search, so the editor starts from the search shown. -->
		{#key data.q}
			<SearchBox
				name={SEARCH_PARAM}
				value={data.q}
				fields={data.fields}
				describedBy={PROBLEM_ID}
				invalid={data.problem !== undefined}
			/>
		{/key}
		{#if data.problem}
			<small id={PROBLEM_ID}>{data.problem}</small>
		{/if}
		<button type="submit">Search</button>
	</form>
	<details>
		<summary>How to search</summary>
		<p>
			A search is terms separated by spaces, such as <code>country:RU,CN path:/wp-*</code>, and
			finds the events that match every term. Start typing a field's name for suggestions.
		</p>
		<ul>
			<li>
				<code>field:value</code> is a term. Repeat a field, or separate values with commas (<code
					>status:403,404</code
				>), and any of its values may match.
			</li>
			<li>
				A <code>-</code> in front turns a term around: <code>-method:GET</code> leaves those out.
			</li>
			<li>
				Text matches whole, ignoring case: <code>*</code> stands for any run of characters and
				<code>?</code> for any one, so <code>user_agent:*zgrab*</code> finds it anywhere.
			</li>
			<li>
				Numbers and times take ranges: <code>requests:&gt;1000</code>,
				<code>date:&gt;=2026-09-01</code>, <code>date:2026-09-01..2026-09-07</code>. Times are in
				UTC: a day, or a minute such as <code>2026-09-01T14:30</code>.
			</li>
			<li>
				Quote a value with spaces or commas in it:
				<code>user_agent:"*KHTML, like Gecko*"</code>.
			</li>
			<li>
				An address or network on its own, such as <code>203.0.113.0/24</code>, means
				<code>ip:</code>.
			</li>
		</ul>
		<figure>
			<table>
				<tbody>
					{#each data.fields as field (field.name)}
						<tr>
							<th scope="row"><code>{field.name}</code></th>
							<td>{field.description}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</figure>
	</details>
</section>

<section>
	{#if data.q}
		<h2>Matching activity</h2>
		<p>Everything that matches the search, newest first. Times are in UTC.</p>
	{:else}
		<h2>Latest activity</h2>
		<p>The most recent attempts from every address, newest first. Times are in UTC.</p>
	{/if}
	{#if data.events === undefined}
		<p>Change the search to see what it finds.</p>
	{:else if data.events.items.length === 0}
		<p>
			{#if !data.isFirstPage}
				There is no older activity.
			{:else if data.q}
				Nothing matches this search.
			{:else}
				Nothing has been recorded yet.
			{/if}
		</p>
	{:else}
		<ActivityTable page={data.events} showAddress />
		<Pagination
			isFirstPage={data.isFirstPage}
			nextCursor={data.events.next_cursor}
			href={pageHref}
		/>
	{/if}
</section>
