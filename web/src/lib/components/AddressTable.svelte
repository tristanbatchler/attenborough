<script lang="ts">
	import { resolve } from '$app/paths';
	import type { AddressActivity } from '$lib/client';
	import CountryFlag from '$lib/components/CountryFlag.svelte';
	import { formatCount, formatSpan } from '$lib/format';

	// Addresses with their all-time totals, each linking to its own page.
	let { rows }: { rows: AddressActivity[] } = $props();
</script>

<figure>
	<table>
		<thead>
			<tr>
				<th scope="col">Address</th>
				<th scope="col">Requests</th>
				<th scope="col">Paths</th>
				<th scope="col">Logins</th>
				<th scope="col">Seen over</th>
			</tr>
		</thead>
		<tbody>
			{#each rows as row (row.ip_address)}
				<tr>
					<td>
						<CountryFlag code={row.country_code} />
						<a href={resolve('/ip/[address]', { address: row.ip_address })}>
							<code>{row.ip_address}</code>
						</a>
					</td>
					<td>{formatCount(row.requests)}</td>
					<td>{formatCount(row.distinct_paths)}</td>
					<td>{formatCount(row.login_attempts)}</td>
					<td>
						{row.first_seen_at && row.last_seen_at
							? formatSpan(row.first_seen_at, row.last_seen_at)
							: '—'}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</figure>
