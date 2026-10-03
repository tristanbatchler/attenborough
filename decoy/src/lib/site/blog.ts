import { resolve } from '$app/paths';
import type { ResolvedPathname } from '$app/types';

// The blog the decoy presents: a small, unofficial fan blog running WordPress. Every page, feed
// and API answer reads from here, so the site agrees with itself. Its theme lives in the content
// only: nothing here names the honeypot's own domain.

export const SITE_NAME = 'League of Draven';
export const TAGLINE = 'An unofficial fan blog for the Glorious Executioner';
export const SITE_DESCRIPTION =
	'Guides, match notes and the occasional moustache appreciation post, by fans, for fans.';
/** The fan-site note a game's community sites carry. */
export const FAN_NOTICE =
	'League of Draven is an unofficial fan site and is not endorsed by or affiliated with the game’s publisher.';

/** The WordPress the site reports (meta generator, feed, REST index). */
export const WORDPRESS_VERSION = '6.6.2';
/** What nginx's PHP-FPM backend adds to every page it generates. */
export const POWERED_BY = 'PHP/8.2.24';

export interface Author {
	id: number;
	/** Also the username they log in with (the API knows it too: ingest.py, AUTHORS). */
	slug: string;
	name: string;
	description: string;
	/** Whether they are the site's administrator, rather than an author. */
	administrator: boolean;
}

export interface Post {
	id: number;
	slug: string;
	title: string;
	/** ISO 8601, UTC. */
	date: string;
	authorId: number;
	excerpt: string;
	paragraphs: string[];
}

export const AUTHORS: Author[] = [
	{
		id: 1,
		slug: 'axespinner',
		name: 'Axe Spinner',
		description: 'Runs the blog. Catches most of the axes. Writes about the ones that got away.',
		administrator: true
	},
	{
		id: 2,
		slug: 'second-axe',
		name: 'Second Axe',
		description: 'Bot lane enthusiast and reluctant support main.',
		administrator: false
	}
];

export const POSTS: Post[] = [
	{
		id: 214,
		slug: 'catching-axes-a-practical-guide',
		title: 'Catching axes: a practical guide',
		date: '2026-08-19T18:42:11Z',
		authorId: 1,
		excerpt:
			'Every Draven player drops an axe eventually. Here is how to drop fewer of them, and how to stop the dropped ones from deciding the game.',
		paragraphs: [
			'Every Draven player drops an axe eventually. The difference between a good game and a long one is usually how many, and when.',
			'Start by deciding where the axe will land before you throw it. Moving towards the next minion you want to hit keeps the catch on your path instead of pulling you off it.',
			'Hold one axe in lane until you are comfortable. Two is greedy; three is a lifestyle choice.',
			'Finally: if the catch would put you under tower, let it go. The axe is replaceable. You are not.'
		]
	},
	{
		id: 198,
		slug: 'a-hundred-games-of-draven',
		title: 'A hundred games of Draven, and what they taught us',
		date: '2026-06-02T09:15:47Z',
		authorId: 2,
		excerpt:
			'We kept notes for a hundred ranked games. Some lessons were about the champion, most were about patience.',
		paragraphs: [
			'We kept notes for a hundred ranked games. Fifty-eight wins, forty-two losses, and one game we have agreed never to discuss.',
			'The clearest pattern: early leads matter more than anything else. Draven wins lanes, and a won lane has to be turned into towers before it fades.',
			'The second pattern: confidence is a resource. Spend it on plays you have practised, not on the ones you saw in a highlight reel.'
		]
	},
	{
		id: 171,
		slug: 'the-moustache-appreciation-post',
		title: 'The moustache appreciation post',
		date: '2026-03-27T20:03:30Z',
		authorId: 1,
		excerpt:
			'A reader asked which skin has the best moustache. We have opinions, and a ranking nobody asked for.',
		paragraphs: [
			'A reader asked which skin has the best moustache. We said we would think about it. We have thought about it for three weeks.',
			'The ranking is in the comments of our forum thread, where it belongs, and where it has already started two arguments.'
		]
	},
	{
		id: 112,
		slug: 'welcome-to-the-league',
		title: 'Welcome to the League',
		date: '2025-11-08T12:00:00Z',
		authorId: 1,
		excerpt:
			'A blog about one champion, written by people who should probably play more than one champion.',
		paragraphs: [
			'This is a blog about one champion, written by people who should probably play more than one champion.',
			'Expect guides, match notes, and the occasional post that is mostly about a moustache. Welcome.'
		]
	}
];

export function authorById(id: number): Author | undefined {
	return AUTHORS.find((author) => author.id === id);
}

export function authorBySlug(slug: string): Author | undefined {
	return AUTHORS.find((author) => author.slug === slug);
}

const YEAR_LENGTH = 4;
const MONTH_END = 7; // "2026-08"

function permalinkParts(post: Post) {
	return {
		year: post.date.slice(0, YEAR_LENGTH),
		month: post.date.slice(YEAR_LENGTH + 1, MONTH_END),
		slug: post.slug
	};
}

/** The post's permalink, WordPress's "month and name" structure: /2026/08/<slug>. */
export function postPath(post: Post): ResolvedPathname {
	return resolve('/[year=year]/[month=month]/[slug]', permalinkParts(post));
}

export function authorPath(author: Author): ResolvedPathname {
	return resolve('/author/[slug]', { slug: author.slug });
}

/** The post at a permalink's year, month and slug, if there is one. */
export function postAt(year: string, month: string, slug: string): Post | undefined {
	return POSTS.find((post) => {
		const parts = permalinkParts(post);
		return parts.year === year && parts.month === month && parts.slug === slug;
	});
}
