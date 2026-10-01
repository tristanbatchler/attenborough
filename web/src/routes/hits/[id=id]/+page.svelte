<script lang="ts">
	import { resolve } from '$app/paths';
	import { formatUtc, requestTarget } from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const hit = $derived(data.hit);
</script>

<svelte:head>
	<title>Request {hit.id} · Attenborough</title>
</svelte:head>

<hgroup>
	<h1>Request {hit.id}</h1>
	<p>One request to the honeypot, exactly as received. Times are in UTC.</p>
</hgroup>

<pre><code>{hit.method} {requestTarget(hit)}</code></pre>

<figure>
	<table>
		<tbody>
			<tr>
				<th scope="row">When</th>
				<td><time datetime={hit.occurred_at}>{formatUtc(hit.occurred_at)}</time></td>
			</tr>
			<tr>
				<th scope="row">Address</th>
				<td>
					<a href={resolve('/ip/[address]', { address: hit.ip_address })}>
						<code>{hit.ip_address}</code>
					</a>
				</td>
			</tr>
			<tr>
				<th scope="row">Status</th>
				<td><code>{hit.status_code}</code></td>
			</tr>
		</tbody>
	</table>
</figure>

<section>
	<h2>Headers</h2>
	<figure>
		<table>
			<tbody>
				{#each Object.entries(hit.headers) as [name, value] (name)}
					<tr>
						<th scope="row"><code>{name}</code></th>
						<td><code>{value}</code></td>
					</tr>
				{/each}
			</tbody>
		</table>
	</figure>
</section>

<section>
	<h2>Body</h2>
	{#if hit.body === null}
		<p>No body was captured.</p>
	{:else if hit.body_size === 0}
		<p>The body was empty.</p>
	{:else}
		<p>
			{hit.body_size} bytes{hit.body_truncated ? ', of which only the start was kept' : ''}. Bytes
			that aren't UTF-8 are shown as <code>\xNN</code>.
		</p>
		<pre><code>{hit.body}</code></pre>
	{/if}
</section>
