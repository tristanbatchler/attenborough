import type { RequestEvent } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { issueCanary } from '$lib/client';
import { apiOptions } from '$lib/server/api';
import { CONTENT_TYPE_HEADER } from '$lib/server/headers';
import { nginxError } from '$lib/server/nginx';
import { requestTarget } from '$lib/server/visit';

// The files a careless admin left in the web root, which secret-hunting scanners ask for more than
// anything but the front page. Each is served with a fresh secret from the API (a canary), recorded
// against the visitor: it opens nothing, but if it is ever tried on the login page, the exhibit can
// say where it came from. The rest of each file is fixed; nothing the visitor sent goes into it.

// nginx's type for files it has no extension mapping for.
const OCTET_STREAM = 'application/octet-stream';
const DATABASE = 'league_of_draven';
const DATABASE_USER = 'draven';

// A WordPress install managed with Bedrock keeps its settings in .env, salts never generated.
const dotEnv = (secret: string) =>
	`DB_NAME='${DATABASE}'\n` +
	`DB_USER='${DATABASE_USER}'\n` +
	`DB_PASSWORD='${secret}'\n` +
	"DB_HOST='localhost'\n" +
	"DB_PREFIX='wp_'\n\n" +
	"WP_ENV='production'\n\n" +
	'# TODO rotate after the tournament stream\n' +
	"AUTH_KEY='generateme'\n" +
	"SECURE_AUTH_KEY='generateme'\n" +
	"LOGGED_IN_KEY='generateme'\n" +
	"NONCE_KEY='generateme'\n";

// An editor's backup of wp-config.php, salts still WordPress's placeholder.
const wpConfigBackup = (secret: string) =>
	'<?php\n' +
	'/** The name of the database for WordPress */\n' +
	`define( 'DB_NAME', '${DATABASE}' );\n\n` +
	'/** Database username */\n' +
	`define( 'DB_USER', '${DATABASE_USER}' );\n\n` +
	'/** Database password */\n' +
	`define( 'DB_PASSWORD', '${secret}' );\n\n` +
	"define( 'DB_HOST', 'localhost' );\n" +
	"define( 'DB_CHARSET', 'utf8mb4' );\n" +
	"define( 'DB_COLLATE', '' );\n\n" +
	"define( 'AUTH_KEY',         'put your unique phrase here' );\n" +
	"define( 'SECURE_AUTH_KEY',  'put your unique phrase here' );\n" +
	"define( 'LOGGED_IN_KEY',    'put your unique phrase here' );\n" +
	"define( 'NONCE_KEY',        'put your unique phrase here' );\n\n" +
	"$table_prefix = 'wp_';\n\n" +
	"define( 'WP_DEBUG', false );\n\n" +
	"if ( ! defined( 'ABSPATH' ) ) {\n\tdefine( 'ABSPATH', __DIR__ . '/' );\n}\n\n" +
	"require_once ABSPATH . 'wp-settings.php';\n";

// A git checkout deployed as the web root, its remote a self-hosted Gitea with the password in the
// URL. The host is this machine's own, so the credential leads to no one else's server; it can
// only come back here.
const gitConfig = (secret: string) =>
	'[core]\n' +
	'\trepositoryformatversion = 0\n' +
	'\tfilemode = true\n' +
	'\tbare = false\n' +
	'\tlogallrefupdates = true\n' +
	'[remote "origin"]\n' +
	`\turl = https://${DATABASE_USER}:${secret}@localhost:3000/${DATABASE_USER}/league-of-draven.git\n` +
	'\tfetch = +refs/heads/*:refs/remotes/origin/*\n' +
	'[branch "main"]\n' +
	'\tremote = origin\n' +
	'\tmerge = refs/heads/main\n';

/** The leaked files, by path (as nginx would match it). */
const LEAKS = new Map<string, (secret: string) => string>([
	['/.env', dotEnv],
	['/wp-config.php.bak', wpConfigBackup],
	['/.git/config', gitConfig]
]);

/**
 * The leaked file at `path`, with a secret the API issued for this visitor; null if no file was
 * leaked there. If the API can't issue a secret, the file isn't there either: nginx's 404.
 */
export async function leak(event: RequestEvent, path: string): Promise<Response | null> {
	const render = LEAKS.get(path);
	if (render === undefined) {
		return null;
	}
	const result = await issueCanary({
		...apiOptions(event),
		body: { path: requestTarget(event).path }
	});
	if (result.data === undefined) {
		console.error('Failed to issue a canary', result.error);
		return nginxError(constants.HTTP_STATUS_NOT_FOUND);
	}
	return new Response(render(result.data.secret), {
		headers: { [CONTENT_TYPE_HEADER]: OCTET_STREAM }
	});
}
