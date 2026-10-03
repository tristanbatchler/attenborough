<script lang="ts">
	import { countryName, flag } from '$lib/geo';

	// Nothing for an address that wasn't located, or whose country isn't known.
	let { code }: { code: string | null | undefined } = $props();
</script>

{#if code}
	<span role="img" aria-label={countryName(code)} title={countryName(code)}>{flag(code)}</span>
{/if}
