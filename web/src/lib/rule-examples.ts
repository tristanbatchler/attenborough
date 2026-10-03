import type { RuleForm } from '$lib/client';

// Starting points for a response rule: pranks to load into the rule form and edit before saving.
// Only text; the API checks and renders them like any rule (api/src/attenborough/rules.py).

export interface RuleExample {
	slug: string;
	name: string;
	description: string;
	rule: RuleForm;
}

const HTML = 'text/html; charset=UTF-8';
const TEXT = 'text/plain; charset=UTF-8';

export const RULE_EXAMPLES: readonly RuleExample[] = [
	{
		slug: 'teapot',
		name: "I'm a teapot",
		description: 'Every request gets 418 and a small teapot.',
		rule: {
			status_code: 418,
			content_type: TEXT,
			body: `I'm a teapot, {{ ip }}.

    __|_|__
   (       )
    \\_____/
`
		}
	},
	{
		slug: 'about-you',
		name: 'A post about you',
		description: 'The front page becomes one post about the visitor, from what the honeypot knows.',
		rule: {
			path_pattern: '/',
			condition: 'requests > 100',
			content_type: HTML,
			body: `<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Hello, visitor</title></head>
<body>
<article>
  <h1>Hello, visitor from {{ city | default: "somewhere" }}</h1>
  <p>
    You have been calling from {{ ip }}{% if network != "" %} on {{ network }} (AS{{ asn }}){% endif %}
    since {{ first_seen | date: "%-d %B %Y" }}: {{ requests }} requests so far.
  </p>
</article>
</body>
</html>
`
		}
	},
	{
		slug: 'molasses',
		name: 'Molasses',
		description: 'Busy visitors wait 15 seconds for every page.',
		rule: {
			condition: 'requests > 1000',
			delay_ms: 15000,
			content_type: HTML,
			body: '<!DOCTYPE html>\n<html><body><p>Loading&hellip;</p></body></html>\n'
		}
	},
	{
		slug: 'everything-exists',
		name: 'Everything exists',
		description: 'Every PHP file a scanner guesses answers 200 with an empty page.',
		rule: { path_pattern: '*.php', content_type: HTML, body: '' }
	},
	{
		slug: 'secrets-everywhere',
		name: 'Secrets everywhere',
		description: 'Every .env file is there, with a fresh canary for a password.',
		rule: {
			path_pattern: '*.env',
			content_type: TEXT,
			body: `APP_ENV=production
APP_DEBUG=false
DB_HOST=127.0.0.1
DB_DATABASE=wordpress
DB_USERNAME=wp_admin
DB_PASSWORD={{ canary }}
`
		}
	},
	{
		slug: 'redirect-maze',
		name: 'Redirect maze',
		description: 'Every page redirects to another, forever. The visitor decides when to stop.',
		rule: {
			path_pattern: '/maze/*',
			status_code: 302,
			content_type: HTML,
			headers: { Location: '/maze/{{ requests }}' }
		}
	},
	{
		slug: 'database-on-fire',
		name: 'Database on fire',
		description: "Every page is WordPress's database error.",
		rule: {
			status_code: 500,
			content_type: HTML,
			body: `<!DOCTYPE html>
<html lang="en-US">
<head><meta charset="UTF-8"><title>Database Error</title></head>
<body id="error-page"><div class="wp-die-message"><h1>Error establishing a database connection</h1></div></body>
</html>
`
		}
	},
	{
		slug: 'come-back-tomorrow',
		name: 'Come back tomorrow',
		description: 'Every request gets 503 and Retry-After: one day. Does anything honour it?',
		rule: {
			status_code: 503,
			content_type: TEXT,
			headers: { 'Retry-After': '86400' },
			body: 'Service Unavailable\n'
		}
	},
	{
		slug: 'already-hacked',
		name: 'Already hacked',
		description: 'The front page is defaced by another crew.',
		rule: {
			path_pattern: '/',
			content_type: HTML,
			body: `<!DOCTYPE html>
<html><head><title>Hacked</title></head>
<body style="background:#000;color:#0f0;font-family:monospace;text-align:center">
<h1>owned.</h1>
<p>This box is ours. You're late, {{ ip }}.</p>
</body></html>
`
		}
	},
	{
		slug: 'every-password-works',
		name: 'Every password works',
		description:
			'Busy guessers get the redirect and cookie of a successful WordPress login. Pair it with Endless update.',
		rule: {
			method: 'POST',
			path_pattern: '/wp-login.php',
			condition: 'logins_10m >= 20',
			status_code: 302,
			content_type: HTML,
			headers: {
				Location: '/wp-admin/',
				'Set-Cookie':
					'wordpress_logged_in_5c3b6e0d=admin%7C{{ now | date: "%s" }}; path=/; HttpOnly'
			}
		}
	},
	{
		slug: 'endless-update',
		name: 'Endless update',
		description: 'wp-admin is forever updating its database, refreshing every 10 seconds.',
		rule: {
			method: 'GET',
			path_pattern: '/wp-admin/*',
			content_type: HTML,
			headers: { Refresh: '10' },
			body: `<!DOCTYPE html>
<html lang="en-US">
<head><meta charset="UTF-8"><title>WordPress &rsaquo; Update</title></head>
<body class="wp-core-ui">
<p class="logo">WordPress</p>
<h1>Database Update Required</h1>
<p>WordPress has been updated! Next and final step, we need to update your database to the newest version.</p>
<p>Updating&hellip;</p>
</body>
</html>
`
		}
	}
];
