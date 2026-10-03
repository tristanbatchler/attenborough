import type { PathCategory } from '$lib/client';

// What each path category (the API's `category`, from the path alone) means to a reader. Every
// category must be here: the Record type fails the build when the API adds one.
export const CATEGORIES: Record<PathCategory, { label: string; description: string }> = {
	homepage: { label: 'Home page', description: 'Just the front page: is anything here?' },
	crawlers: {
		label: 'Crawler files',
		description: 'robots.txt, favicons, security.txt: what search engines and scanners index.'
	},
	secrets: {
		label: 'Secrets & config',
		description:
			'.env files, Git repositories, cloud keys and app config, left where anyone can read them.'
	},
	backups: {
		label: 'Backups & logs',
		description: 'Database dumps, archives and log files left in the web root.'
	},
	debug: {
		label: 'Debug pages',
		description: 'phpinfo, Spring actuators, profilers: pages that leak how a server is set up.'
	},
	exploits: {
		label: 'Known exploits',
		description:
			'Probes for specific, published vulnerabilities in routers, appliances and frameworks.'
	},
	wordpress: {
		label: 'WordPress',
		description: 'The login page, XML-RPC and admin pages of the most-attacked web software.'
	},
	webshells: {
		label: 'Web shells',
		description: 'Randomly named PHP files: someone looking for a backdoor another attacker left.'
	},
	logins: {
		label: 'Login pages',
		description: 'Sign-in pages of VPNs, firewalls, mail servers and admin consoles.'
	},
	apis: {
		label: 'APIs',
		description: 'GraphQL, REST, container and AI-agent endpoints.'
	},
	other: { label: 'Other', description: 'Anything the rules above don’t recognise.' }
};
