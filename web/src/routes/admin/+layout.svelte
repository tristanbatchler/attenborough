<script lang="ts">
	import { resolve } from '$app/paths';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();
</script>

<nav aria-label="Admin">
	<ul>
		<li><strong>Admin</strong></li>
		<li><a href={resolve('/admin')}>Bans</a></li>
		<li><a href={resolve('/admin/audit')}>Audit log</a></li>
	</ul>
	<ul>
		<li>
			<form method="POST" action={resolve('/auth/logout')}>
				<button type="submit">Log out</button>
			</form>
		</li>
	</ul>
</nav>
<p><small>Logged in as {data.me.name} ({data.me.email}).</small></p>

{@render children()}
