<script lang="ts">
	import Layout from './Layout.svelte';
	import { type Post, authorById, authorPath, postPath } from './blog';
	import { displayDate } from './dates';

	// The front page (every post) or an author's archive (theirs): titles, bylines and excerpts.
	let { title, heading, posts }: { title: string; heading: string | null; posts: Post[] } =
		$props();
</script>

<Layout {title}>
	{#if heading}
		<header class="page-header"><h1 class="page-title">{heading}</h1></header>
	{/if}
	{#each posts as post (post.id)}
		{@const author = authorById(post.authorId)}
		<article id="post-{post.id}" class="post-{post.id} post type-post status-publish hentry">
			<header class="entry-header">
				<h2 class="entry-title"><a href={postPath(post)} rel="bookmark">{post.title}</a></h2>
				<div class="entry-meta">
					<time class="entry-date published" datetime={post.date}>{displayDate(post.date)}</time>
					{#if author}
						by <a href={authorPath(author)}>{author.name}</a>
					{/if}
				</div>
			</header>
			<div class="entry-summary"><p>{post.excerpt}</p></div>
		</article>
	{/each}
</Layout>
