<script lang="ts">
	import { resolve } from '$app/paths';
	import { CATEGORIES } from '$lib/categories';
	import type { EventPage } from '$lib/client';
	import CountryFlag from '$lib/components/CountryFlag.svelte';
	import { formatUtc, requestTarget } from '$lib/format';

	// The feed shows every address, with its country's flag; an IP's own page doesn't.
	let { page, showAddress = false }: { page: EventPage; showAddress?: boolean } = $props();
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
				<th scope="col">Details</th>
			</tr>
		</thead>
		<tbody>
			{#each page.items as event (`${event.kind}-${String(event.id)}`)}
				<tr>
					<td><time datetime={event.occurred_at}>{formatUtc(event.occurred_at)}</time></td>
					{#if showAddress}
						<td>
							<CountryFlag code={page.locations[event.ip_address]?.country_code} />
							<a href={resolve('/ip/[address]', { address: event.ip_address })}>
								<code>{event.ip_address}</code>
							</a>
						</td>
					{/if}
					{#if event.kind === 'hit'}
						<td>
							Request
							<small>{CATEGORIES[event.category].label}</small>
						</td>
						<td>
							<a href={resolve('/hits/[id=id]', { id: String(event.id) })}>
								<code>{event.method} {requestTarget(event)}</code>
							</a>
							→ <code>{event.status_code}</code>
							{#if event.body_preview}
								<samp>{event.body_preview}</samp>
								<small
									>{event.body_size} bytes{event.body_truncated ? ', preview cut short' : ''}</small
								>
							{/if}
						</td>
					{:else if event.kind === 'login_attempt'}
						<td>Login attempt</td>
						<td>
							<code>{event.username}</code> / <code>{event.password}</code> at
							<code>{event.path}</code>
							{#if event.decoy_accepted}(the decoy pretended to accept it){/if}
						</td>
					{:else if event.kind === 'decoy_view'}
						<td>{event.decoy_type === 'binary' ? 'Decoy download' : 'Decoy view'}</td>
						<td><code>{event.decoy_slug}</code></td>
					{:else}
						<td>Decoy password</td>
						<td>
							<code>{event.decoy_slug}</code>
							({event.decoy_accepted ? 'accepted by the decoy' : 'rejected by the decoy'})
						</td>
					{/if}
				</tr>
			{/each}
		</tbody>
	</table>
</figure>
