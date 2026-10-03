<script lang="ts">
	import { untrack } from 'svelte';
	import type { Attachment } from 'svelte/attachments';
	import type { Marker } from '$lib/client';
	import { createEditor, type Editor, type EditorMode } from '$lib/editor';

	// A <textarea> form field, which becomes a code editor once the page's JavaScript runs.
	let {
		name,
		value,
		mode,
		markers
	}: { name: string; value: string; mode: EditorMode; markers: readonly Marker[] } = $props();

	let editor: Editor | undefined;

	// Created once: a change of mode reconfigures the editor (below), keeping what was typed.
	const enhance: Attachment<HTMLTextAreaElement> = (textarea) => {
		editor = createEditor(
			textarea,
			untrack(() => mode),
			markers
		);
		return () => {
			editor?.destroy();
			editor = undefined;
		};
	};

	$effect(() => {
		// Read first, so the effect follows `mode` even if it runs before the editor exists.
		const current = mode;
		editor?.setMode(current);
	});
</script>

<textarea {name} {value} rows="16" spellcheck="false" {@attach enhance}></textarea>
