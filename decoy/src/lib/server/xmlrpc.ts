import type { RequestEvent } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { setTimeout as sleep } from 'node:timers/promises';
import { reportXmlrpcLogins, type Credentials } from '$lib/client';
import { apiOptions } from '$lib/server/api';
import { escapeXml } from '$lib/server/blog';
import {
	CONTENT_TYPE_HEADER,
	POWERED_BY_HEADER,
	TEXT_CONTENT_TYPE,
	XML_CONTENT_TYPE
} from '$lib/server/headers';
import { requestTarget } from '$lib/server/visit';
import { authorBySlug, SITE_NAME } from '$lib/site/blog';

// xmlrpc.php, as WordPress's (wp_xmlrpc_server, on IXR) answers it. The logins are the point:
// wp.getUsersBlogs, alone or many to a system.multicall, is how most WordPress brute force guesses,
// so every username and password in a request is reported (/ingest/logins/xmlrpc), which decides
// which open. Every other call fails as a wrong login, as before. The body is recorded with the hit
// like any other. Nothing a visitor sends is put into a response.

const RSD_QUERY = 'rsd';
// Where the blog and this server are, as the RSD document and getUsersBlogs give them.
const HOME_PATH = '/';
const XMLRPC_PATH = '/xmlrpc.php';
const XMLRPC_POST_ONLY = 'XML-RPC server accepts POST requests only.';
const ALLOW_HEADER = 'allow';

const MULTICALL = 'system.multicall';
// The login calls, and where in their parameters the username is (the password follows it):
// blogger.getUsersBlogs takes an app key first; wp.getUsersBlogs is it without one.
// A login's parameters: the username, then the password.
const CREDENTIAL_PARAMS = 2;
const LOGIN_CALLS = new Map([
	['wp.getUsersBlogs', 0],
	['blogger.getUsersBlogs', 1]
]);
// The elements of an XML-RPC call, and the members of a multicall's entry.
const METHOD_CALL = 'methodCall';
const METHOD_NAME = 'methodName';
const PARAMS = 'params';
const PARAM = 'param';
const VALUE = 'value';
const ARRAY = 'array';
const DATA = 'data';
const STRUCT = 'struct';
const MEMBER = 'member';
const NAME = 'name';

interface Fault {
	faultCode: number;
	faultString: string;
}

function fault(faultCode: number, faultString: string): Fault {
	return { faultCode, faultString };
}

// The XML-RPC spec's fault codes (IXR's), and WordPress's own, which are HTTP statuses.
const NOT_WELL_FORMED = -32700;
const INVALID_REQUEST = -32600;
const INVALID_PARAMS = -32602;

// The faults this server gives, with WordPress's codes and words.
const PARSE_ERROR = fault(NOT_WELL_FORMED, 'parse error. not well formed');
const NOT_A_METHOD_CALL = fault(
	INVALID_REQUEST,
	'server error. invalid xml-rpc. not conforming to spec. Request must be a methodCall'
);
const NOT_A_CALL_LIST = fault(
	INVALID_REQUEST,
	'server error. invalid xml-rpc. system.multicall expects an array of method calls'
);
const NOT_A_CALL = fault(
	INVALID_REQUEST,
	'server error. invalid xml-rpc. Each multicall entry must be a struct with a string methodName'
);
const PARAMS_NOT_A_LIST = fault(
	INVALID_PARAMS,
	'server error. invalid method parameters. Each multicall entry params must be an array'
);
const RECURSIVE_MULTICALL = fault(
	INVALID_REQUEST,
	'Recursive calls to system.multicall are forbidden'
);
const TOO_FEW_ARGUMENTS = fault(
	constants.HTTP_STATUS_BAD_REQUEST,
	'Insufficient arguments passed to this XML-RPC method.'
);
const NOT_STRINGS = fault(
	constants.HTTP_STATUS_BAD_REQUEST,
	'The username and password arguments should be strings.'
);
const BAD_LOGIN = fault(constants.HTTP_STATUS_FORBIDDEN, 'Incorrect username or password.');

/** A value as IXR parses it: every scalar as its text, arrays, and structs by member name. */
type Value = string | Value[] | Map<string, Value>;

/** An XML element, as far as XML-RPC needs one: its child elements and its own text. */
interface Element {
	name: string;
	children: Element[];
	text: string;
}

// One piece of XML: CDATA, a declaration or comment (skipped), a tag, or text. Sticky (`y`), so a
// token is only ever looked for where the last one ended, and no two parts of a tag can match the
// same characters: a body is scanned in linear time, whatever a visitor sends. (Without both, a
// 4 KB body of `<` took seconds, and the decoy answers nothing else meanwhile.)
const XML_TOKEN =
	/<!\[CDATA\[([\s\S]*?)\]\]>|<(?:\?|!(?!\[CDATA\[))[^>]*>|<(\/?)([A-Za-z_][^\s/>]*)(?:\s[^>]*?)?(\/?)>|([^<]+)/gy;
// How deep elements may nest, as libxml2 allows by default: value() recurses once per level.
const MAX_DEPTH = 256;
const ENTITY = /&(?:#x([0-9a-f]+)|#([0-9]+)|(lt|gt|amp|quot|apos));/gi;
const NAMED_ENTITIES = new Map([
	['lt', '<'],
	['gt', '>'],
	['amp', '&'],
	['quot', '"'],
	['apos', "'"]
]);
const HEX = 16;
const MAX_CODE_POINT = 0x10ffff;

function decodeEntities(text: string): string {
	return text.replace(ENTITY, (whole, hex?: string, decimal?: string, name?: string) => {
		if (name !== undefined) {
			return NAMED_ENTITIES.get(name.toLowerCase()) ?? whole;
		}
		const code = hex === undefined ? Number(decimal) : parseInt(hex, HEX);
		return code <= MAX_CODE_POINT ? String.fromCodePoint(code) : whole;
	});
}

/** The document's one root element, or null if it isn't well-formed enough to have one. */
function parseXml(xml: string): Element | null {
	const document: Element = { name: '', children: [], text: '' };
	const ancestors: Element[] = [];
	let current = document;
	let at = 0;
	for (const token of xml.matchAll(XML_TOKEN)) {
		at += token[0].length;
		const [, cdata, closing, name, selfClosing, text] = token;
		if (cdata !== undefined) {
			current.text += cdata;
		} else if (text !== undefined) {
			current.text += decodeEntities(text);
		} else if (name === undefined) {
			continue;
		} else if (closing) {
			const parent = ancestors.pop();
			if (parent === undefined || current.name !== name) {
				return null;
			}
			current = parent;
		} else {
			const element: Element = { name, children: [], text: '' };
			current.children.push(element);
			if (!selfClosing) {
				if (ancestors.length === MAX_DEPTH) {
					return null;
				}
				ancestors.push(current);
				current = element;
			}
		}
	}
	// A sticky scan stops at the first thing that isn't a token: anything left unread is malformed.
	const [root, ...others] = document.children;
	return at === xml.length && current === document && others.length === 0 ? (root ?? null) : null;
}

function child(element: Element | undefined, name: string): Element | undefined {
	return element?.children.find((found) => found.name === name);
}

function childrenNamed(element: Element | undefined, name: string): Element[] {
	return element?.children.filter((found) => found.name === name) ?? [];
}

/** A `<value>`: untyped, it is a string; typed, its scalar's text, or its array or struct. */
function value(element: Element | undefined): Value {
	const [typed] = element?.children ?? [];
	if (typed === undefined) {
		return element?.text ?? '';
	}
	if (typed.name === ARRAY) {
		return childrenNamed(child(typed, DATA), VALUE).map(value);
	}
	if (typed.name === STRUCT) {
		return new Map(
			childrenNamed(typed, MEMBER).map((member) => [
				child(member, NAME)?.text ?? '',
				value(child(member, VALUE))
			])
		);
	}
	return typed.text;
}

/** One call to make: a fault already, or a login to report, whose outcome decides it. */
type Call = Fault | Credentials;

function isFault(made: Call | XmlValue): made is Fault {
	return typeof made === 'object' && !Array.isArray(made) && 'faultCode' in made;
}

/** What WordPress's login() makes of a call to `method` with `params`, before checking them. */
function call(method: string, params: Value[]): Call {
	if (method === MULTICALL) {
		return RECURSIVE_MULTICALL;
	}
	const at = LOGIN_CALLS.get(method);
	if (at === undefined) {
		return BAD_LOGIN;
	}
	// IXR passes a lone parameter on its own, not in a list, which every method then refuses.
	if (params.length < at + CREDENTIAL_PARAMS) {
		return TOO_FEW_ARGUMENTS;
	}
	const [username, password] = params.slice(at, at + CREDENTIAL_PARAMS);
	if (typeof username !== 'string' || typeof password !== 'string') {
		return NOT_STRINGS;
	}
	return { username, password };
}

/** Each call in a system.multicall, in order, as IXR's multiCall() takes them. */
function multicall(calls: Value | undefined): Call[] | Fault {
	if (!Array.isArray(calls)) {
		return NOT_A_CALL_LIST;
	}
	return calls.map((entry) => {
		const method = entry instanceof Map ? entry.get(METHOD_NAME) : undefined;
		if (!(entry instanceof Map) || typeof method !== 'string') {
			return NOT_A_CALL;
		}
		const params = entry.get(PARAMS) ?? [];
		return Array.isArray(params) ? call(method, params) : PARAMS_NOT_A_LIST;
	});
}

/** Which of `logins` open, in order; none if the API can't be asked. Waits out its tarpit. */
async function attemptLogins(event: RequestEvent, logins: Credentials[]): Promise<boolean[]> {
	if (logins.length === 0) {
		return [];
	}
	const result = await reportXmlrpcLogins({
		...apiOptions(event),
		body: { path: requestTarget(event).path, attempts: logins }
	});
	if (result.data === undefined) {
		console.error('Failed to report XML-RPC logins', result.error);
		return logins.map(() => false);
	}
	await sleep(result.data.delay_ms);
	return result.data.successes;
}

/** What blogger.getUsersBlogs answers a login: the one blog, and whether they administer it. */
function usersBlogs(username: string): XmlValue {
	const author = authorBySlug(username.toLowerCase());
	return [
		{
			// An install's account is its administrator.
			isAdmin: author?.administrator ?? true,
			url: HOME_PATH,
			blogid: '1',
			blogName: SITE_NAME,
			xmlrpc: XMLRPC_PATH
		}
	];
}

/** A value to answer with, as IXR_Value types PHP's: booleans, ints, strings, lists, structs. */
type XmlValue = boolean | number | string | XmlValue[] | { [name: string]: XmlValue };

/** IXR_Value::getXml(), including its line breaks. */
function xmlValue(data: XmlValue): string {
	if (typeof data === 'boolean') {
		return `<boolean>${data ? '1' : '0'}</boolean>`;
	}
	if (typeof data === 'number') {
		return `<int>${String(data)}</int>`;
	}
	if (typeof data === 'string') {
		return `<string>${escapeXml(data)}</string>`;
	}
	if (Array.isArray(data)) {
		const items = data.map((item) => `  <value>${xmlValue(item)}</value>\n`);
		return `<array><data>\n${items.join('')}</data></array>`;
	}
	const members = Object.entries(data).map(
		([name, member]) =>
			`  <member><name>${escapeXml(name)}</name><value>${xmlValue(member)}</value></member>\n`
	);
	return `<struct>\n${members.join('')}</struct>`;
}

const XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n';

function xmlResponse(xml: string): Response {
	return new Response(XML_DECLARATION + xml, {
		headers: { ...POWERED_BY_HEADER, [CONTENT_TYPE_HEADER]: XML_CONTENT_TYPE }
	});
}

/** IXR_Server::serve()'s answer: the result, in IXR's layout. */
function resultResponse(result: XmlValue): Response {
	return xmlResponse(
		'<methodResponse>\n  <params>\n    <param>\n      <value>\n' +
			`      ${xmlValue(result)}\n` +
			'      </value>\n    </param>\n  </params>\n</methodResponse>\n'
	);
}

/** IXR_Error::getXml(). Still 200 OK: WordPress sets a fault's code as the status only when
 * XML-RPC is disabled. */
function faultResponse({ faultCode, faultString }: Fault): Response {
	return xmlResponse(
		'<methodResponse>\n  <fault>\n    <value>\n      <struct>\n' +
			'        <member>\n          <name>faultCode</name>\n' +
			`          <value><int>${String(faultCode)}</int></value>\n        </member>\n` +
			'        <member>\n          <name>faultString</name>\n' +
			`          <value><string>${escapeXml(faultString)}</string></value>\n` +
			'        </member>\n      </struct>\n    </value>\n  </fault>\n</methodResponse>\n'
	);
}

/**
 * xmlrpc.php: a GET gets WordPress's refusal (or the RSD document, `?rsd`); a POST is parsed as
 * IXR does, and its logins reported and answered as the API decides.
 */
export async function xmlrpc(event: RequestEvent): Promise<Response> {
	const { request, url } = event;
	if (request.method !== constants.HTTP2_METHOD_POST) {
		if (url.searchParams.has(RSD_QUERY)) {
			return rsd();
		}
		return new Response(XMLRPC_POST_ONLY, {
			status: constants.HTTP_STATUS_METHOD_NOT_ALLOWED,
			headers: {
				...POWERED_BY_HEADER,
				[CONTENT_TYPE_HEADER]: TEXT_CONTENT_TYPE,
				[ALLOW_HEADER]: constants.HTTP2_METHOD_POST
			}
		});
	}
	const root = parseXml(await request.text());
	if (root === null) {
		return faultResponse(PARSE_ERROR);
	}
	const method = child(root, METHOD_NAME)?.text.trim();
	if (root.name !== METHOD_CALL || method === undefined) {
		return faultResponse(NOT_A_METHOD_CALL);
	}
	const params = childrenNamed(child(root, PARAMS), PARAM).map((param) =>
		value(child(param, VALUE))
	);
	if (method !== MULTICALL) {
		const made = call(method, params);
		const [opened = false] = await attemptLogins(event, isFault(made) ? [] : [made]);
		const result = outcome(made, opened);
		return isFault(result) ? faultResponse(result) : resultResponse(result);
	}
	const calls = multicall(params[0]);
	if (!Array.isArray(calls)) {
		return faultResponse(calls);
	}
	const opened = await attemptLogins(
		event,
		calls.filter((made): made is Credentials => !isFault(made))
	);
	let login = 0;
	// Each call's result in a list of its own, or its fault as a struct (a copy: an interface
	// isn't an XmlValue struct to TypeScript, an object literal is).
	return resultResponse(
		calls.map((made) => {
			const result = outcome(made, !isFault(made) && opened[login++] === true);
			return isFault(result) ? { ...result } : [result];
		})
	);
}

/** A call's result: its fault, the blogs of a login that opened, or a wrong login's fault. */
function outcome(made: Call, opened: boolean): Fault | XmlValue {
	if (isFault(made)) {
		return made;
	}
	return opened ? usersBlogs(made.username) : BAD_LOGIN;
}

function rsd(): Response {
	const xml =
		'<?xml version="1.0" encoding="UTF-8"?><rsd version="1.0" xmlns="http://archipelago.phrasewise.com/rsd">\n' +
		'\t<service>\n\t\t<engineName>WordPress</engineName>\n\t\t<engineLink>https://wordpress.org/</engineLink>\n' +
		`\t\t<homePageLink>${HOME_PATH}</homePageLink>\n\t\t<apis>\n` +
		`\t\t\t<api name="WordPress" blogID="1" preferred="true" apiLink="${XMLRPC_PATH}" />\n` +
		'\t\t</apis>\n\t</service>\n</rsd>\n';
	return new Response(xml, {
		headers: { ...POWERED_BY_HEADER, [CONTENT_TYPE_HEADER]: XML_CONTENT_TYPE }
	});
}
