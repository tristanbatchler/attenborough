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
							{#if event.banned}<small>refused: banned</small>{/if}
							{#if event.custom_response}<small>custom response</small>{/if}
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
							{#if event.canary}
								<small>
									A planted password: the honeypot handed it out in
									<code>{event.canary.path}</code> to
									<a href={resolve('/ip/[address]', { address: event.canary.ip_address })}
										><code>{event.canary.ip_address}</code></a
									>,
									<time datetime={event.canary.issued_at}>{formatUtc(event.canary.issued_at)}</time
									>.
								</small>
							{/if}
							{#if event.install}
								<small>
									An account created through the decoy's installer, by
									<a href={resolve('/ip/[address]', { address: event.install.ip_address })}
										><code>{event.install.ip_address}</code></a
									>,
									<time datetime={event.install.attempted_at}
										>{formatUtc(event.install.attempted_at)}</time
									>:
									<a href={resolve('/installs/[id=id]', { id: String(event.install.id) })}
										>the whole takeover</a
									>.
								</small>
							{/if}
						</td>
					{:else if event.kind === 'install_attempt'}
						<td>WordPress install</td>
						<td>
							<code>{event.username}</code> / <code>{event.password}</code>, email
							<code>{event.email}</code>, site title <code>{event.site_title}</code>, at
							<code>{event.path}</code>
							(the decoy pretended to install it):
							<a href={resolve('/installs/[id=id]', { id: String(event.id) })}>the whole takeover</a
							>
							{#if event.password_generated}
								<small>No password was chosen: the decoy's installer made this one up.</small>
							{/if}
						</td>
					{/if}
				</tr>
			{/each}
		</tbody>
	</table>
</figure>
