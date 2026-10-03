import { redirect } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { POWERED_BY } from '$lib/site/blog';
import { ADMIN_PATH, LOGIN_PATH } from '$lib/wordpress/site';
import {
	CONTENT_TYPE_HEADER,
	HTML_CONTENT_TYPE,
	TEXT_CONTENT_TYPE,
	XML_CONTENT_TYPE
} from '$lib/server/headers';

// The parts of WordPress every install has besides the blog: the admin area's front door,
// XML-RPC, the installer and the readme. Fixed content; nothing a visitor sends is put into it.

const INSTALLER = 'install.php';
const POWERED_BY_HEADER = { 'x-powered-by': POWERED_BY };
const RSD_QUERY = 'rsd';

/** Any admin page while logged out: WordPress sends you to the login, and back here after. */
export function adminPage(rest: string): Response {
	if (rest === INSTALLER) {
		return installedPage();
	}
	const back = encodeURIComponent(`${ADMIN_PATH}${rest}`);
	redirect(constants.HTTP_STATUS_FOUND, `${LOGIN_PATH}?redirect_to=${back}&reauth=1`);
}

/** wp-admin/install.php on a site that is already set up, which is what scanners hope it isn't. */
function installedPage(): Response {
	const html =
		'<!DOCTYPE html>\n<html lang="en-US">\n<head>\n<meta charset="utf-8" />\n' +
		'<title>WordPress &rsaquo; Installation</title>\n</head>\n<body class="wp-core-ui">\n' +
		'<p id="logo">WordPress</p>\n<h1>Already Installed</h1>\n' +
		'<p>You appear to have already installed WordPress. To reinstall please clear your old ' +
		'database tables first.</p>\n<p class="step"><a href="/wp-login.php" class="button button-large">Log In</a></p>\n' +
		'</body>\n</html>\n';
	return new Response(html, {
		headers: { ...POWERED_BY_HEADER, [CONTENT_TYPE_HEADER]: HTML_CONTENT_TYPE }
	});
}

const XMLRPC_POST_ONLY = 'XML-RPC server accepts POST requests only.';

function xmlrpcFault(code: number, message: string): Response {
	const xml =
		'<?xml version="1.0" encoding="UTF-8"?>\n<methodResponse>\n  <fault>\n    <value>\n      <struct>\n' +
		`        <member><name>faultCode</name><value><int>${String(code)}</int></value></member>\n` +
		`        <member><name>faultString</name><value><string>${message}</string></value></member>\n` +
		'      </struct>\n    </value>\n  </fault>\n</methodResponse>\n';
	return new Response(xml, {
		headers: { ...POWERED_BY_HEADER, [CONTENT_TYPE_HEADER]: XML_CONTENT_TYPE }
	});
}

const XMLRPC_PARSE_ERROR = -32700;
const XMLRPC_BAD_LOGIN = 403;

/**
 * xmlrpc.php: a GET gets WordPress's refusal (or the RSD document, `?rsd`); a POST gets the fault
 * for wrong credentials, which is what every authenticated call gets here. The body is recorded
 * with the hit like any other.
 */
export async function xmlrpc(request: Request, url: URL): Promise<Response> {
	if (request.method !== constants.HTTP2_METHOD_POST) {
		if (url.searchParams.has(RSD_QUERY)) {
			return rsd();
		}
		return new Response(XMLRPC_POST_ONLY, {
			status: constants.HTTP_STATUS_METHOD_NOT_ALLOWED,
			headers: { ...POWERED_BY_HEADER, [CONTENT_TYPE_HEADER]: TEXT_CONTENT_TYPE }
		});
	}
	const body = await request.text();
	return body.includes('<methodCall>')
		? xmlrpcFault(XMLRPC_BAD_LOGIN, 'Incorrect username or password.')
		: xmlrpcFault(XMLRPC_PARSE_ERROR, 'parse error. not well formed');
}

function rsd(): Response {
	const xml =
		'<?xml version="1.0" encoding="UTF-8"?><rsd version="1.0" xmlns="http://archipelago.phrasewise.com/rsd">\n' +
		'\t<service>\n\t\t<engineName>WordPress</engineName>\n\t\t<engineLink>https://wordpress.org/</engineLink>\n' +
		'\t\t<homePageLink>/</homePageLink>\n\t\t<apis>\n' +
		'\t\t\t<api name="WordPress" blogID="1" preferred="true" apiLink="/xmlrpc.php" />\n' +
		'\t\t</apis>\n\t</service>\n</rsd>\n';
	return new Response(xml, {
		headers: { ...POWERED_BY_HEADER, [CONTENT_TYPE_HEADER]: XML_CONTENT_TYPE }
	});
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
