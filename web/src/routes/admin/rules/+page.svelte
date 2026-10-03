<script lang="ts">
	import { resolve } from '$app/paths';
	import { RULE_FIELDS } from '$lib/admin';
	import { formatCount, formatUtc } from '$lib/format';
	import { EXAMPLE_PARAM } from '$lib/params';
	import { RULE_EXAMPLES } from '$lib/rule-examples';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
</script>

<svelte:head>
	<title>Rules · Admin · Attenborough</title>
</svelte:head>

<hgroup>
	<h1>Response rules</h1>
	<p>
		What the decoy answers instead of its own page. The first rule whose method, path and condition
		match a request answers it; bans come before every rule. The exhibit only says that a custom
		response was sent. Times are in UTC.
	</p>
</hgroup>

{#if form?.message}
	<p role="alert">{form.message}</p>
{/if}

{#if data.rules.length === 0}
	<p>No rules yet: the decoy answers everything itself.</p>
{:else}
	<figure>
		<table>
			<thead>
				<tr>
					<th scope="col">#</th>
					<th scope="col">When</th>
					<th scope="col">Then</th>
					<th scope="col">Until</th>
					<th scope="col">Answered</th>
					<th scope="col"></th>
				</tr>
			</thead>
			<tbody>
				{#each data.rules as rule, index (rule.id)}
					<tr>
						<td>{index + 1}</td>
						<td>
							<a href={resolve('/admin/rules/[id=id]', { id: String(rule.id) })}>
								<code>{rule.method ?? 'any'} {rule.path_pattern ?? '*'}</code>
							</a>
							{#if rule.condition}<br /><small><code>{rule.condition}</code></small>{/if}
							{#if rule.note}<br /><small>{rule.note}</small>{/if}
						</td>
						<td><code>{rule.status_code}</code> <small>{rule.content_type}</small></td>
						<td>
							{#if rule.expires === null}
								No end
							{:else}
								<time datetime={rule.expires}>{formatUtc(rule.expires)}</time>
							{/if}
						</td>
						<td>{formatCount(rule.hits)}</td>
						<td>
							<form method="POST" action="?/move">
								<input type="hidden" name={RULE_FIELDS.ruleId} value={rule.id} />
								<button
									name={RULE_FIELDS.direction}
									value="up"
									aria-label="Move up"
									disabled={index === 0}>↑</button
								>
								<button
									name={RULE_FIELDS.direction}
									value="down"
									aria-label="Move down"
									disabled={index === data.rules.length - 1}>↓</button
								>
							</form>
							<form method="POST" action="?/remove">
								<input type="hidden" name={RULE_FIELDS.ruleId} value={rule.id} />
								<button>Remove</button>
							</form>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</figure>
{/if}

<section>
	<h2>New rule</h2>
	<p><a href={resolve('/admin/rules/new')}>Start from nothing</a>, or from an example:</p>
	<ul>
		{#each RULE_EXAMPLES as example (example.slug)}
			<li>
				<a href={resolve(`/admin/rules/new?${EXAMPLE_PARAM}=${example.slug}`)}>{example.name}</a>:
				{example.description}
			</li>
		{/each}
	</ul>
</section>
