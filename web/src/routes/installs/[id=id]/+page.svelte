<script lang="ts">
	import { resolve } from '$app/paths';
	import CountryFlag from '$lib/components/CountryFlag.svelte';
	import { formatCount, formatGap, formatUtc } from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const install = $derived(data.takeover.install);
	const logins = $derived(data.takeover.logins);
	const locations = $derived(data.takeover.locations);
	const addresses = $derived(new Set([install.ip_address, ...logins.map((l) => l.ip_address)]));
	// When the step before a login came: the login before it, or for the first, the install.
	const previous = (index: number) => logins[index - 1]?.occurred_at ?? install.occurred_at;
</script>

<svelte:head>
	<title>Takeover {install.id} · Attenborough</title>
</svelte:head>

<hgroup>
	<h1>Takeover attempt {install.id}</h1>
	<p>
		Someone finished the decoy's "unfinished" WordPress install to become its administrator, and
		these are the logins into the account it created, from every address. Nothing was installed, and
		nothing was logged in to: the decoy only pretended. Times are in UTC.
	</p>
</hgroup>

<p>
	{formatCount(data.takeover.login_count)}
	{data.takeover.login_count === 1 ? 'login' : 'logins'} into the account, from
	{addresses.size}
	{addresses.size === 1 ? 'address' : 'addresses'} in all.
	{#if data.takeover.login_count > logins.length}
		The first {formatCount(logins.length)} are listed.
	{/if}
</p>

<figure>
	<table>
		<thead>
			<tr>
				<th scope="col">When</th>
				<th scope="col">After the step before</th>
				<th scope="col">Address</th>
				<th scope="col">Step</th>
				<th scope="col">Details</th>
			</tr>
		</thead>
		<tbody>
			<tr>
				<td><time datetime={install.occurred_at}>{formatUtc(install.occurred_at)}</time></td>
				<td></td>
				<td>
					<CountryFlag code={locations[install.ip_address]?.country_code} />
					<a href={resolve('/ip/[address]', { address: install.ip_address })}>
						<code>{install.ip_address}</code>
					</a>
				</td>
				<td>Install</td>
				<td>
					<code>{install.username}</code> / <code>{install.password}</code>, email
					<code>{install.email}</code>, site title <code>{install.site_title}</code>
					{#if install.password_generated}
						<small>No password was chosen: the decoy's installer made this one up.</small>
					{/if}
				</td>
			</tr>
			{#each logins as login, index (login.id)}
				<tr>
					<td><time datetime={login.occurred_at}>{formatUtc(login.occurred_at)}</time></td>
					<td>{formatGap(previous(index), login.occurred_at)}</td>
					<td>
						<CountryFlag code={locations[login.ip_address]?.country_code} />
						<a href={resolve('/ip/[address]', { address: login.ip_address })}>
							<code>{login.ip_address}</code>
						</a>
					</td>
					<td>Login</td>
					<td>
						<code>{login.username}</code> / <code>{login.password}</code> at
						<code>{login.path}</code>
						({login.decoy_accepted ? 'the decoy pretended to accept it' : 'rejected by the decoy'})
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</figure>
