<script lang="ts">
	import Layout from './Layout.svelte';
	import { type Post, SITE_NAME, authorById, authorPath } from './blog';
	import { displayDate } from './dates';

	let { post }: { post: Post } = $props();
	const author = $derived(authorById(post.authorId));
</script>

<Layout title="{post.title} &#8211; {SITE_NAME}">
	<article id="post-{post.id}" class="post-{post.id} post type-post status-publish hentry">
		<header class="entry-header">
			<h1 class="entry-title">{post.title}</h1>
			<div class="entry-meta">
				<time class="entry-date published" datetime={post.date}>{displayDate(post.date)}</time>
				{#if author}
					by <a href={authorPath(author)}>{author.name}</a>
				{/if}
			</div>
		</header>
		<div class="entry-content">
			{#each post.paragraphs as paragraph, index (index)}
				<p>{paragraph}</p>
			{/each}
		</div>
	</article>
	<p class="comments-closed">Comments are closed.</p>
</Layout>
