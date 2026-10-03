<script lang="ts" generics="Row extends { addresses: number }">
	import type { Snippet } from 'svelte';
	import { formatCount } from '$lib/format';

	// A ranked list of things (paths, countries, passwords...): each row's name, its count with a
	// bar relative to the largest, and how many addresses it came from.
	let {
		rows,
		heading,
		countHeading,
		count,
		name,
		empty
	}: {
		rows: Row[];
		heading: string;
		countHeading: string;
		count: (row: Row) => number;
		name: Snippet<[Row]>;
		empty: string;
	} = $props();

	const largest = $derived(Math.max(...rows.map(count)));
</script>

{#if rows.length === 0}
	<p>{empty}</p>
{:else}
	<figure>
		<table>
			<thead>
				<tr>
					<th scope="col">{heading}</th>
					<th scope="col">{countHeading}</th>
					<th scope="col">Addresses</th>
				</tr>
			</thead>
			<tbody>
				{#each rows as row, index (index)}
					<tr>
						<td>{@render name(row)}</td>
						<td>
							{formatCount(count(row))}
							<meter value={count(row)} max={largest}></meter>
						</td>
						<td>{formatCount(row.addresses)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</figure>
{/if}
