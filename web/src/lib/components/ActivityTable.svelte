<script lang="ts">
	import { resolve } from '$app/paths';
	import type { ListIpActivityRow } from '$lib/client';
	import { formatUtc } from '$lib/format';

	// Rows from the recent-activity feed carry the visitor's address; rows for one IP don't.
	type Row = ListIpActivityRow & { ip_address?: string };

	let { rows }: { rows: Row[] } = $props();

	const showAddress = $derived(rows.some((row) => row.ip_address !== undefined));
</script>

<figure>
	<table>
		<thead>
			<tr>
				<th scope="col">When</th>
				{#if showAddress}
					<th scope="col">Address</th>
				{/if}
				<th scope="col">Event</th>
				<th scope="col">Target</th>
				<th scope="col">Details</th>
			</tr>
		</thead>
		<tbody>
			{#each rows as row, index (index)}
				<tr>
					<td><time datetime={row.event_at}>{formatUtc(row.event_at)}</time></td>
					{#if showAddress && row.ip_address !== undefined}
						<td>
							<a href={resolve('/ip/[address]', { address: row.ip_address })}>
								<code>{row.ip_address}</code>
							</a>
						</td>
					{/if}
					<td>{row.event_type}</td>
					<td><code>{row.target_slug}</code></td>
					<td><code>{row.details}</code></td>
				</tr>
			{/each}
		</tbody>
	</table>
</figure>
