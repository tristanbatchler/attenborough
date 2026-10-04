<script lang="ts">
	import { untrack } from 'svelte';
	import type { Attachment } from 'svelte/attachments';
	import type { SearchFieldHelp } from '$lib/client';
	import type { SearchEditor } from '$lib/search-editor';

	// The search field: an <input>, which becomes an editor that completes the search's fields and
	// values once the page's JavaScript runs.
	let {
		name,
		value,
		fields,
		describedBy,
		invalid
	}: {
		name: string;
		value: string;
		fields: readonly SearchFieldHelp[];
		describedBy: string;
		invalid: boolean;
	} = $props();

	const enhance: Attachment<HTMLInputElement> = (input) => {
		let editor: SearchEditor | undefined;
		let removed = false;
		const known = untrack(() => fields);
		void import('$lib/search-editor').then(({ createSearchEditor }) => {
			if (!removed) editor = createSearchEditor(input, known);
		});
		return () => {
			removed = true;
			editor?.destroy();
		};
	};
</script>

<input
	{name}
	{value}
	type="search"
	placeholder="country:RU,CN path:/wp-* -method:GET date:>=2026-09-01"
	aria-label="Search"
	aria-describedby={describedBy}
	aria-invalid={invalid ? 'true' : undefined}
	autocomplete="off"
	spellcheck="false"
	{@attach enhance}
/>
