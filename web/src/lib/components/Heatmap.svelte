<script lang="ts">
	import type { DayActivity } from '$lib/client';
	import { formatCount, formatUtcDay } from '$lib/format';

	// Requests per hour, one row per UTC day: a cell's shade is its share of the busiest hour, at
	// most 60% of the theme's colour so that its number stays readable.
	let { days }: { days: DayActivity[] } = $props();

	const HOUR_DIGITS = 2;
	const busiest = $derived(Math.max(1, ...days.flatMap((day) => day.requests_by_hour)));
	const hours = $derived(days[0]?.requests_by_hour.map((_, hour) => hour) ?? []);
	const hourName = (hour: number) => String(hour).padStart(HOUR_DIGITS, '0');
</script>

<figure>
	<table>
		<thead>
			<tr>
				<th scope="col">Day (UTC)</th>
				{#each hours as hour (hour)}
					<th scope="col">{hourName(hour)}</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each days as day (day.day)}
				<tr>
					<th scope="row">{formatUtcDay(day.day)}</th>
					{#each day.requests_by_hour as requests, hour (hour)}
						<td
							style:--level={requests / busiest}
							title="{formatUtcDay(day.day)}, {hourName(hour)}:00 UTC: {formatCount(
								requests
							)} requests"
						>
							{requests === 0 ? '' : formatCount(requests)}
						</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
</figure>

<style>
	table {
		font-size: 0.7em;
		font-variant-numeric: tabular-nums;
	}

	th,
	td {
		padding: 0.3em;
		text-align: center;
		white-space: nowrap;
	}

	td {
		background: color-mix(
			in srgb,
			var(--pico-primary-background) calc(var(--level) * 60%),
			transparent
		);
	}
</style>
