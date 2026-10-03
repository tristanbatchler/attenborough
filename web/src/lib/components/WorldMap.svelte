<script lang="ts">
	import type { MapPoint } from '$lib/geo';
	import { LAND } from '$lib/world.gen';

	// The land in degrees (equirectangular: x = longitude, y = -latitude; src/lib/world.gen.ts),
	// from 84°N to 60°S: nothing scans the honeypot from Antarctica.
	const NORTH = 84;
	const SOUTH = -60;
	const WEST = -180;
	const WIDTH = 360;
	// Point radii in degrees: by area, the heaviest point the largest.
	const MIN_RADIUS = 1.2;
	const MAX_RADIUS = 5;

	let { points, label }: { points: MapPoint[]; label: string } = $props();

	const heaviest = $derived(Math.max(...points.map((point) => point.weight)));
	// Heaviest first, so smaller points are drawn on top and stay visible.
	const drawn = $derived(
		points
			.toSorted((a, b) => b.weight - a.weight)
			.map((point) => ({
				...point,
				radius: MIN_RADIUS + (MAX_RADIUS - MIN_RADIUS) * Math.sqrt(point.weight / heaviest)
			}))
	);
</script>

<svg viewBox="{WEST} {-NORTH} {WIDTH} {NORTH - SOUTH}" role="img" aria-label={label}>
	<path d={LAND} />
	{#each drawn as point, index (index)}
		<circle cx={point.longitude} cy={-point.latitude} r={point.radius}>
			<title>{point.title}</title>
		</circle>
	{/each}
</svg>

<style>
	svg {
		display: block;
		width: 100%;
		height: auto;
		margin-bottom: var(--pico-spacing);
	}

	path {
		fill: var(--pico-muted-border-color);
	}

	circle {
		fill: var(--pico-primary);
		fill-opacity: 0.55;
		stroke: var(--pico-primary);
		stroke-width: 0.3;
	}
</style>
