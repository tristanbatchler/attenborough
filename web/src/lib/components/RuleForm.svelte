<script lang="ts">
	import type { Marker, Preview } from '$lib/client';
	import { DURATIONS, HTTP_METHODS, KEEP_EXPIRY, RULE_FIELDS } from '$lib/admin';
	import { editorMode } from '$lib/editor';
	import { formatUtc } from '$lib/format';
	import type { PreviewInput, RuleValues } from '$lib/admin';
	import CodeEditor from './CodeEditor.svelte';

	// The response rule form, for a new rule or a saved one: what to match, what to answer, and a
	// preview of the answer for any address. The API checks everything on save.
	let {
		values,
		markers,
		previewInput,
		preview,
		message,
		isSaved
	}: {
		values: RuleValues;
		markers: readonly Marker[];
		previewInput: PreviewInput;
		preview: Preview | undefined;
		message: string | undefined;
		isSaved: boolean;
	} = $props();

	const CONTENT_TYPES = [
		'text/html; charset=UTF-8',
		'text/plain; charset=UTF-8',
		'application/json; charset=UTF-8',
		'text/xml; charset=UTF-8'
	];
	const CONTENT_TYPE_LIST = 'content-types';

	// Follows the field as it is edited, so the editor highlights the body in its language.
	let contentType = $derived(values.contentType);
	const mode = $derived(editorMode(contentType));
</script>

{#if message}
	<div role="alert"><pre>{message}</pre></div>
{/if}

<form method="POST" action="?/save">
	<fieldset>
		<legend><strong>When</strong> <small>(blank: anything)</small></legend>
		<label>
			Method
			<select name={RULE_FIELDS.method} value={values.method}>
				<option value="">Any</option>
				{#each HTTP_METHODS as method (method)}
					<option value={method}>{method}</option>
				{/each}
			</select>
		</label>
		<label>
			Path
			<input
				name={RULE_FIELDS.pathPattern}
				value={values.pathPattern}
				placeholder="/wp-login.php, *.env, /wp-content/*"
				autocomplete="off"
			/>
		</label>
		<label>
			Condition <small>(Liquid, as inside <code>{'{% if … %}'}</code>)</small>
			<input
				name={RULE_FIELDS.condition}
				value={values.condition}
				placeholder="country == &quot;RU&quot; and logins_10m >= 20"
				autocomplete="off"
				spellcheck="false"
			/>
		</label>
	</fieldset>

	<fieldset>
		<legend><strong>Then answer</strong></legend>
		<label>
			Status
			<input
				name={RULE_FIELDS.statusCode}
				value={values.statusCode}
				type="number"
				min="200"
				max="599"
				required
			/>
		</label>
		<label>
			Content type
			<input
				name={RULE_FIELDS.contentType}
				bind:value={contentType}
				list={CONTENT_TYPE_LIST}
				autocomplete="off"
				required
			/>
			<datalist id={CONTENT_TYPE_LIST}>
				{#each CONTENT_TYPES as type (type)}
					<option value={type}></option>
				{/each}
			</datalist>
		</label>
		<label>
			Delay <small>(ms, at most 15000)</small>
			<input name={RULE_FIELDS.delayMs} value={values.delayMs} type="number" min="0" max="15000" />
		</label>
		<label>
			Headers <small>(one <code>Name: value</code> per line; values are Liquid)</small>
			<textarea name={RULE_FIELDS.headers} value={values.headers} rows="2" spellcheck="false"
			></textarea>
		</label>
		<label for={RULE_FIELDS.body}>Body <small>(Liquid)</small></label>
		<CodeEditor name={RULE_FIELDS.body} value={values.body} {mode} {markers} />
	</fieldset>

	<fieldset>
		<label>
			For
			<select name={RULE_FIELDS.duration} value={values.duration}>
				{#if isSaved}
					<option value={KEEP_EXPIRY}>
						{values.currentExpiry ? `Until ${formatUtc(values.currentExpiry)}` : 'Until removed'} (as
						now)
					</option>
				{/if}
				{#each DURATIONS as duration (duration.value)}
					<option value={duration.value}>{duration.label}</option>
				{/each}
			</select>
			<input type="hidden" name={RULE_FIELDS.currentExpiry} value={values.currentExpiry} />
		</label>
		<label>
			Note <small>(private)</small>
			<input name={RULE_FIELDS.note} value={values.note} autocomplete="off" />
		</label>
	</fieldset>

	<fieldset>
		<legend
			><strong>Preview</strong>
			<small>(as if this address sent this request; issues no canary)</small></legend
		>
		<input
			name={RULE_FIELDS.previewIp}
			value={previewInput.ip}
			aria-label="Address"
			autocomplete="off"
		/>
		<input
			name={RULE_FIELDS.previewMethod}
			value={previewInput.method}
			aria-label="Method"
			autocomplete="off"
		/>
		<input
			name={RULE_FIELDS.previewPath}
			value={previewInput.path}
			aria-label="Path"
			autocomplete="off"
		/>
		<button type="submit" formaction="?/preview">Preview</button>
	</fieldset>

	<button type="submit">{isSaved ? 'Save' : 'Create'}</button>
</form>

{#if preview}
	<section>
		<h2>Preview</h2>
		<p>
			{preview.matches
				? 'This rule would answer that request:'
				: "This rule wouldn't answer that request (its method, path or condition don't match). If it did:"}
		</p>
		<pre><code
				>{preview.response.status_code}
Content-Type: {preview.response.content_type}
{#each Object.entries(preview.response.headers) as [name, value] (name)}{name}: {value}
				{/each}{#if preview.response.delay_ms > 0}(after {preview.response.delay_ms} ms)
				{/if}
{preview.response.body}</code
			></pre>
	</section>
{/if}

<section>
	<h2>Markers</h2>
	<p>The same in the condition, header values and body. Liquid's tags and filters work too.</p>
	<figure>
		<table>
			<tbody>
				{#each markers as marker (marker.name)}
					<tr>
						<th scope="row"><code>{marker.name}</code></th>
						<td>{marker.description}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</figure>
</section>
