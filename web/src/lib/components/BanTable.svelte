<script lang="ts">
	import type { Snippet } from 'svelte';
	import { resolve } from '$app/paths';
	import type { BanRecord } from '$lib/client';
	import { formatUtc } from '$lib/format';

	// The admin area's bans, in full: who made each and why. Never used on the public exhibit.
	let { bans, actions }: { bans: BanRecord[]; actions?: Snippet<[BanRecord]> } = $props();
</script>

<figure>
	<table>
		<thead>
			<tr>
				<th scope="col">Address</th>
				<th scope="col">Banned</th>
				<th scope="col">Until</th>
				<th scope="col">Reason</th>
				<th scope="col">Status</th>
				{#if actions}<th scope="col"></th>{/if}
			</tr>
		</thead>
		<tbody>
			{#each bans as ban (ban.id)}
				<tr>
					<td>
						<a href={resolve('/admin/ip/[address]', { address: ban.ip_address })}>
							<code>{ban.ip_address}</code>
						</a>
					</td>
					<td>
						<time datetime={ban.added}>{formatUtc(ban.added)}</time>
						<small>by {ban.added_by}</small>
					</td>
					<td>
						{#if ban.expires === null}
							Never
						{:else}
							<time datetime={ban.expires}>{formatUtc(ban.expires)}</time>
						{/if}
					</td>
					<td>{ban.reason ?? ''}</td>
					<td>
						{#if ban.active}
							Active
						{:else if ban.revoked_at !== null}
							Revoked <time datetime={ban.revoked_at}>{formatUtc(ban.revoked_at)}</time>
							<small
								>by {ban.revoked_by}{ban.revocation_reason
									? `: ${ban.revocation_reason}`
									: ''}</small
							>
						{:else}
							Expired
						{/if}
					</td>
					{#if actions}<td>{@render actions(ban)}</td>{/if}
				</tr>
			{/each}
		</tbody>
	</table>
</figure>
