<script lang="ts">
	import RuleForm from '$lib/components/RuleForm.svelte';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
</script>

<svelte:head>
	<title>New rule · Admin · Attenborough</title>
</svelte:head>

<h1>New response rule</h1>

<RuleForm
	values={form?.values ?? data.values}
	markers={data.markers}
	previewInput={form?.previewInput ?? data.previewInput}
	preview={form && 'preview' in form ? form.preview : undefined}
	message={form && 'message' in form ? form.message : undefined}
	isSaved={false}
/>
