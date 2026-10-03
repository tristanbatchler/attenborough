<script lang="ts">
	import { resolve } from '$app/paths';
	import { BAN_DURATIONS, BAN_ID_FIELD, DURATION_FIELD, REASON_FIELD } from '$lib/bans';
	import BanTable from '$lib/components/BanTable.svelte';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	const activeBan = $derived(data.bans.find((ban) => ban.active));
</script>

<svelte:head>
	<title>{data.address} · Admin · Attenborough</title>
</svelte:head>

<hgroup>
	<h1>Bans of <code>{data.address}</code></h1>
	<p>
		<a href={resolve('/ip/[address]', { address: data.address })}>Its activity on the exhibit</a>.
		Times are in UTC.
	</p>
</hgroup>

{#if form?.message}
	<p role="alert">{form.message}</p>
{/if}

{#if activeBan}
	<section>
		<h2>Revoke the ban</h2>
		<form method="POST" action="?/revoke">
			<input type="hidden" name={BAN_ID_FIELD} value={activeBan.id} />
			<label>
				Reason <small>(optional, private)</small>
				<input name={REASON_FIELD} type="text" autocomplete="off" />
			</label>
			<button type="submit">Revoke</button>
		</form>
	</section>
{:else}
	<section>
		<h2>Ban this address</h2>
		<form method="POST" action="?/ban">
			<label>
				For
				<select name={DURATION_FIELD} required>
					{#each BAN_DURATIONS as duration (duration.value)}
						<option value={duration.value}>{duration.label}</option>
					{/each}
				</select>
			</label>
			<label>
				Reason <small>(optional, private: the exhibit only shows that it is banned)</small>
				<input name={REASON_FIELD} type="text" autocomplete="off" />
			</label>
			<button type="submit">Ban</button>
		</form>
	</section>
{/if}

<section>
	<h2>History</h2>
	{#if data.bans.length === 0}
		<p>This address has never been banned.</p>
	{:else}
		<BanTable bans={data.bans} />
	{/if}
</section>
