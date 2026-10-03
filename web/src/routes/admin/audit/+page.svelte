<script lang="ts">
	import { resolve } from '$app/paths';
	import { formatUtc } from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head>
	<title>Audit log · Admin · Attenborough</title>
</svelte:head>

<hgroup>
	<h1>Audit log</h1>
	<p>Every admin action, the latest first. Times are in UTC.</p>
</hgroup>

{#if data.entries.length === 0}
	<p>Nothing has been done yet.</p>
{:else}
	<figure>
		<table>
			<thead>
				<tr>
					<th scope="col">When</th>
					<th scope="col">Who</th>
					<th scope="col">What</th>
					<th scope="col">Address</th>
					<th scope="col">Details</th>
				</tr>
			</thead>
			<tbody>
				{#each data.entries as entry (entry.id)}
					<tr>
						<td><time datetime={entry.logged_at}>{formatUtc(entry.logged_at)}</time></td>
						<td>{entry.email}</td>
						<td>{entry.action}</td>
						<td>
							{#if entry.target_ip !== null}
								<a href={resolve('/admin/ip/[address]', { address: entry.target_ip })}>
									<code>{entry.target_ip}</code>
								</a>
							{/if}
						</td>
						<td><code>{entry.details}</code></td>
					</tr>
				{/each}
			</tbody>
		</table>
	</figure>
{/if}
