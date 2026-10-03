import { redirect, type RequestEvent } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { ADMIN_PATH, LOGIN_PATH } from '$lib/wordpress/site';
import { CONTENT_TYPE_HEADER, HTML_CONTENT_TYPE } from '$lib/server/headers';
import { installer } from '$lib/server/install';
import { wpDie } from '$lib/server/wp-die';

// The parts of WordPress every install has besides the blog: the admin area's front door,
// the installer ($lib/server/install) and the readme. Fixed content; nothing a visitor
// sends is put into it, except what the installer repeats back, escaped, as WordPress does.

const INSTALLER = 'install.php';
const SETUP_CONFIG = 'setup-config.php';

/**
 * Any page under wp-admin/. The installer and setup-config.php work without logging in, as they
 * must before there is anyone to log in as; anything else sends you to the login, and back after.
 */
export async function adminPage(rest: string, event: RequestEvent): Promise<Response> {
	if (rest === INSTALLER) {
		return installer(event);
	}
	if (rest === SETUP_CONFIG) {
		return configExists();
	}
	const back = encodeURIComponent(`${ADMIN_PATH}${rest}`);
	redirect(constants.HTTP_STATUS_FOUND, `${LOGIN_PATH}?redirect_to=${back}&reauth=1`);
}

/** setup-config.php once wp-config.php exists: WordPress refuses, and points to the installer. */
function configExists(): Response {
	return wpDie(
		'<p>The file <code>wp-config.php</code> already exists. If you need to reset any of the ' +
			'configuration items in this file, please delete it first. You may try ' +
			`<a href="${INSTALLER}">installing now</a>.</p>`,
		constants.HTTP_STATUS_CONFLICT
	);
}

/** readme.html, as WordPress ships it (shortened). */
export function readme(): Response {
	const html =
		'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta name="viewport" content="width=device-width" />\n' +
		'<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />\n' +
		'<title>WordPress &#8250; ReadMe</title>\n</head>\n<body>\n' +
		'<h1 id="logo">WordPress</h1>\n<p style="text-align: center">Semantic Personal Publishing Platform</p>\n' +
		'<h2>First Things First</h2>\n<p>Welcome. WordPress is a very special project to me. ' +
		'Every developer and contributor adds something unique to the mix, and together we create ' +
		'something beautiful that I am proud to be a part of.</p>\n' +
		'<p style="text-align: right">&#8212; Matt Mullenweg</p>\n' +
		'<h2>Installation: Famous 5-minute install</h2>\n<ol>\n' +
		'<li>Unzip the package in an empty directory and upload everything.</li>\n' +
		'<li>Open <span class="file"><a href="wp-admin/install.php">wp-admin/install.php</a></span> in your browser.</li>\n' +
		'</ol>\n</body>\n</html>\n';
	return new Response(html, { headers: { [CONTENT_TYPE_HEADER]: HTML_CONTENT_TYPE } });
}
