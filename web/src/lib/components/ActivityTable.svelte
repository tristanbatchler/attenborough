<script lang="ts">
	import { resolve } from '$app/paths';
	import type { EventPage } from '$lib/client';
	import { formatUtc, requestTarget } from '$lib/format';

	// The feed shows every address, so it adds an address column; an IP's own page doesn't.
	let { events, showAddress = false }: { events: EventPage['items']; showAddress?: boolean } =
		$props();
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
			{#each events as event (`${event.kind}-${String(event.id)}`)}
				<tr>
					<td><time datetime={event.occurred_at}>{formatUtc(event.occurred_at)}</time></td>
					{#if showAddress}
						<td>
							<a href={resolve('/ip/[address]', { address: event.ip_address })}>
								<code>{event.ip_address}</code>
							</a>
						</td>
					{/if}
					{#if event.kind === 'hit'}
						<td>Request</td>
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
