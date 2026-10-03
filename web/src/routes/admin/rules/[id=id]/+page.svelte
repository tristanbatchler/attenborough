<script lang="ts">
	import RuleForm from '$lib/components/RuleForm.svelte';
	import { formatCount, formatUtc } from '$lib/format';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
</script>

<svelte:head>
	<title>Rule {data.rule.id} · Admin · Attenborough</title>
</svelte:head>

<hgroup>
	<h1>Response rule {data.rule.id}</h1>
	<p>
		Answered {formatCount(data.rule.hits)} requests. Last changed
		<time datetime={data.rule.updated}>{formatUtc(data.rule.updated)}</time>.
	</p>
</hgroup>

<RuleForm
	values={form?.values ?? data.values}
	markers={data.markers}
	previewInput={form?.previewInput ?? data.previewInput}
	preview={form && 'preview' in form ? form.preview : undefined}
	message={form && 'message' in form ? form.message : undefined}
	isSaved={true}
/>
