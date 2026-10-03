import { redirect } from '@sveltejs/kit';
import { constants } from 'node:http2';
import {
	AUTHORS,
	type Author,
	POSTS,
	POWERED_BY,
	type Post,
	SITE_NAME,
	TAGLINE,
	WORDPRESS_VERSION,
	authorById,
	authorPath,
	postPath
} from '$lib/site/blog';
import { feedDate } from '$lib/site/dates';
import PostList from '$lib/site/PostList.svelte';
import PostPage from '$lib/site/PostPage.svelte';
import {
	CONTENT_TYPE_HEADER,
	JSON_CONTENT_TYPE,
	RSS_CONTENT_TYPE,
	TEXT_CONTENT_TYPE
} from '$lib/server/headers';
import { htmlPage } from '$lib/server/html';
import { nginxError } from '$lib/server/nginx';

// The blog's responses: its pages, REST API, feed and the small files every WordPress has. All of
// it is fixed content from $lib/site/blog; nothing a visitor sends is put into a response.

const REST_PREFIX = '/wp-json';
const REST_INDEX = '/';
const REST_USERS = '/wp/v2/users';
const REST_POSTS = '/wp/v2/posts';
const USER_ID = /^\/wp\/v2\/users\/(\d+)\/?$/;

/** The query parameters WordPress routes `/` and `/index.php` by. */
export const QueryVar = {
	REST_ROUTE: 'rest_route',
	AUTHOR: 'author',
	FEED: 'feed',
	POST: 'p'
} as const;

// What every page WordPress generates carries: PHP's banner, and where its REST API is.
const WORDPRESS_HEADERS = {
	'x-powered-by': POWERED_BY,
	link: `<${REST_PREFIX}/>; rel="https://api.w.org/"`
};

const FRONT_PAGE_CLASS = 'home blog';

export function frontPage(): Response {
	return htmlPage(
		PostList,
		{ title: `${SITE_NAME} – ${TAGLINE}`, heading: null, posts: POSTS },
		{ headers: WORDPRESS_HEADERS, bodyClass: FRONT_PAGE_CLASS }
	);
}

export function postPage(post: Post): Response {
	return htmlPage(
		PostPage,
		{ post },
		{
			headers: WORDPRESS_HEADERS,
			bodyClass: `post-template-default single single-post postid-${String(post.id)}`
		}
	);
}

export function authorPage(author: Author): Response {
	return htmlPage(
		PostList,
		{
			title: `${author.name} – ${SITE_NAME}`,
			heading: `Author: ${author.name}`,
			posts: POSTS.filter((post) => post.authorId === author.id)
		},
		{
			headers: WORDPRESS_HEADERS,
			bodyClass: `archive author author-${author.slug} author-${String(author.id)}`
		}
	);
}

function json(body: unknown, status: number = constants.HTTP_STATUS_OK): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { ...WORDPRESS_HEADERS, [CONTENT_TYPE_HEADER]: JSON_CONTENT_TYPE }
	});
}

function restUser(author: Author) {
	return {
		id: author.id,
		name: author.name,
		url: '',
		description: author.description,
		link: authorPath(author),
		slug: author.slug,
		meta: []
	};
}

function restPost(post: Post) {
	return {
		id: post.id,
		date: post.date.replace('Z', ''),
		date_gmt: post.date.replace('Z', ''),
		slug: post.slug,
		status: 'publish',
		type: 'post',
		link: postPath(post),
		title: { rendered: post.title },
		excerpt: { rendered: `<p>${post.excerpt}</p>\n`, protected: false },
		author: post.authorId
	};
}

const REST_NO_ROUTE = {
	code: 'rest_no_route',
	message: 'No route was found matching the URL and request method.',
	data: { status: constants.HTTP_STATUS_NOT_FOUND }
};

const REST_INVALID_USER = {
	code: 'rest_user_invalid_id',
	message: 'Invalid user ID.',
	data: { status: constants.HTTP_STATUS_NOT_FOUND }
};

/** The REST API's answer for `route` (after /wp-json, or a `rest_route` query parameter). */
export function rest(route: string): Response {
	const normalised = route === '' ? REST_INDEX : route.replace(/\/$/, '') || REST_INDEX;
	if (normalised === REST_INDEX) {
		return json({
			name: SITE_NAME,
			description: TAGLINE,
			url: '',
			home: '',
			gmt_offset: 0,
			timezone_string: '',
			namespaces: ['oembed/1.0', 'wp/v2', 'wp-site-health/v1'],
			authentication: [],
			routes: {}
		});
	}
	if (normalised === REST_USERS) {
		return json(AUTHORS.map(restUser));
	}
	if (normalised === REST_POSTS) {
		return json(POSTS.map(restPost));
	}
	const user = USER_ID.exec(normalised);
	if (user) {
		const author = authorById(Number(user[1]));
		return author
			? json(restUser(author))
			: json(REST_INVALID_USER, constants.HTTP_STATUS_NOT_FOUND);
	}
	return json(REST_NO_ROUTE, constants.HTTP_STATUS_NOT_FOUND);
}

function escapeXml(text: string): string {
	return text
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;')
		.replaceAll('"', '&quot;');
}

/** The RSS feed, as WordPress writes /feed/. */
export function feed(): Response {
	const items = POSTS.map((post) => {
		const author = authorById(post.authorId);
		return (
			`\t<item>\n\t\t<title>${escapeXml(post.title)}</title>\n` +
			`\t\t<link>${postPath(post)}</link>\n` +
			`\t\t<dc:creator><![CDATA[${author?.name ?? ''}]]></dc:creator>\n` +
			`\t\t<pubDate>${feedDate(post.date)}</pubDate>\n` +
			`\t\t<guid isPermaLink="false">?p=${String(post.id)}</guid>\n` +
			`\t\t<description><![CDATA[${post.excerpt}]]></description>\n\t</item>`
		);
	}).join('\n');
	const latest = POSTS[0]?.date ?? new Date(0).toISOString();
	const xml =
		'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"\n' +
		'\txmlns:dc="http://purl.org/dc/elements/1.1/"\n>\n\n<channel>\n' +
		`\t<title>${escapeXml(SITE_NAME)}</title>\n\t<link>/</link>\n` +
		`\t<description>${escapeXml(TAGLINE)}</description>\n` +
		`\t<lastBuildDate>${feedDate(latest)}</lastBuildDate>\n\t<language>en-US</language>\n` +
		`\t<generator>https://wordpress.org/?v=${WORDPRESS_VERSION}</generator>\n` +
		items +
		'\n</channel>\n</rss>\n';
	return new Response(xml, {
		headers: { ...WORDPRESS_HEADERS, [CONTENT_TYPE_HEADER]: RSS_CONTENT_TYPE }
	});
}

/** WordPress's virtual robots.txt. */
export function robots(): Response {
	return new Response('User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n', {
		headers: { ...WORDPRESS_HEADERS, [CONTENT_TYPE_HEADER]: TEXT_CONTENT_TYPE }
	});
}

/**
 * `/` and `/index.php`: WordPress routes them by query parameters before it shows the front page.
 * Anything it doesn't know falls through to the front page, as WordPress's does.
 */
export function home(url: URL): Response {
	const query = url.searchParams;
	const route = query.get(QueryVar.REST_ROUTE);
	if (route !== null) {
		return rest(route);
	}
	const authorId = query.get(QueryVar.AUTHOR);
	if (authorId !== null) {
		const author = authorById(Number(authorId));
		// WordPress redirects ?author=N to the author's archive, which is how scanners list users.
		if (author) {
			redirect(constants.HTTP_STATUS_MOVED_PERMANENTLY, authorPath(author));
		}
		return nginxError(constants.HTTP_STATUS_NOT_FOUND);
	}
	if (query.get(QueryVar.FEED) !== null) {
		return feed();
	}
	const postId = query.get(QueryVar.POST);
	if (postId !== null) {
		const post = POSTS.find((candidate) => String(candidate.id) === postId);
		if (post) {
			redirect(constants.HTTP_STATUS_MOVED_PERMANENTLY, postPath(post));
		}
	}
	return frontPage();
}
