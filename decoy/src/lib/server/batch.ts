import { constants } from 'node:http2';
import { AUTHORS, POSTS } from '$lib/site/blog';
import { CONTENT_TYPE_HEADER, NOCACHE_HEADERS } from '$lib/server/headers';
import { REST_NO_ROUTE, errorStatus, restError, type RestError } from '$lib/server/rest-errors';

// The REST API's batch endpoint (POST /wp-json/batch/v1, since WordPress 5.6), as an anonymous
// visitor gets it from WordPress 6.6.2: every sub-request is checked and answered with the error
// WordPress gives it (nothing can be created, edited or deleted without logging in), all in one
// 207. Scanners use it to smuggle requests past filters that only look at the URL. Nothing is
// executed; the whole body is recorded with the hit.

export const BATCH_ROUTE = '/batch/v1';

const MAX_BATCH_SIZE = 25;
const BATCH_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE'];
const DEFAULT_METHOD = 'POST';
const DELETE_METHOD = 'DELETE';
const VALIDATION_MODES = ['require-all-validate', 'normal'];
const REQUIRE_ALL_VALID = 'require-all-validate';
const VALIDATION_FAILED = 'validation';
const Param = { VALIDATION: 'validation', REQUESTS: 'requests' } as const;
const Property = { METHOD: 'method', PATH: 'path', BODY: 'body' } as const;
const SchemaType = { STRING: 'string', ARRAY: 'array', OBJECT: 'object' } as const;
const JSON_CONTENT_TYPE = 'application/json';

// PHP's json_last_error() for malformed JSON, and its message.
const JSON_ERROR_SYNTAX = 4;
const JSON_ERROR_SYNTAX_MESSAGE = 'Syntax error';

const BAD_REQUEST = constants.HTTP_STATUS_BAD_REQUEST;
const NOT_FOUND = constants.HTTP_STATUS_NOT_FOUND;
// rest_authorization_required_code() for a visitor who isn't logged in.
const UNAUTHORIZED = constants.HTTP_STATUS_UNAUTHORIZED;

const BATCH_NOT_ALLOWED = restError(
	'rest_batch_not_allowed',
	'The requested route does not support batch requests.',
	BAD_REQUEST
);
const CANNOT_CREATE_POST = restError(
	'rest_cannot_create',
	'Sorry, you are not allowed to create posts as this user.',
	UNAUTHORIZED
);
const CANNOT_EDIT_POST = restError(
	'rest_cannot_edit',
	'Sorry, you are not allowed to edit this post.',
	UNAUTHORIZED
);
const CANNOT_DELETE_POST = restError(
	'rest_cannot_delete',
	'Sorry, you are not allowed to delete this post.',
	UNAUTHORIZED
);
const INVALID_POST = restError('rest_post_invalid_id', 'Invalid post ID.', NOT_FOUND);
const CANNOT_CREATE_TERM = restError(
	'rest_cannot_create',
	'Sorry, you are not allowed to create terms in this taxonomy.',
	UNAUTHORIZED
);
const CANNOT_EDIT_TERM = restError(
	'rest_cannot_update',
	'Sorry, you are not allowed to edit this term.',
	UNAUTHORIZED
);
const CANNOT_DELETE_TERM = restError(
	'rest_cannot_delete',
	'Sorry, you are not allowed to delete this term.',
	UNAUTHORIZED
);
const INVALID_TERM = restError('rest_term_invalid', 'Term does not exist.', NOT_FOUND);
const CANNOT_CREATE_USER = restError(
	'rest_cannot_create_user',
	'Sorry, you are not allowed to create new users.',
	UNAUTHORIZED
);
const CANNOT_EDIT_USER = restError(
	'rest_cannot_edit',
	'Sorry, you are not allowed to edit this user.',
	UNAUTHORIZED
);
const CANNOT_DELETE_USER = restError(
	'rest_user_cannot_delete',
	'Sorry, you are not allowed to delete this user.',
	UNAUTHORIZED
);
const INVALID_USER = restError('rest_user_invalid_id', 'Invalid user ID.', NOT_FOUND);

// WordPress 6.6.2 turns a path parse_url() can't read (`http://:`) into a WP_Error, then passes it
// to match_request_to_handler(), which calls a method WP_Error doesn't have: a fatal error, which
// WordPress answers (for a JSON request, with WP_DEBUG_DISPLAY at its default) like this. Scanners
// send such a path first to tell a WordPress with the batch API from anything else.
const DOCUMENT_ROOT = '/var/www/html';
const REST_SERVER = `${DOCUMENT_ROOT}/wp-includes/rest-api/class-wp-rest-server.php`;
const FATAL_LINE = 1091;
const E_ERROR = 1;
const FATAL_MESSAGE =
	`Uncaught Error: Call to undefined method WP_Error::get_method() in ${REST_SERVER}:${String(FATAL_LINE)}\n` +
	'Stack trace:\n' +
	`#0 ${REST_SERVER}(1691): WP_REST_Server->match_request_to_handler(Object(WP_Error))\n` +
	`#1 ${REST_SERVER}(1230): WP_REST_Server->serve_batch_request_v1(Object(WP_REST_Request))\n` +
	`#2 ${REST_SERVER}(1063): WP_REST_Server->respond_to_request(Object(WP_REST_Request), '/batch/v1', Array, NULL)\n` +
	`#3 ${REST_SERVER}(439): WP_REST_Server->dispatch(Object(WP_REST_Request))\n` +
	`#4 ${DOCUMENT_ROOT}/wp-includes/rest-api.php(420): WP_REST_Server->serve_request('/batch/v1')\n` +
	`#5 ${DOCUMENT_ROOT}/wp-includes/class-wp-hook.php(324): rest_api_loaded(Object(WP))\n` +
	`#6 ${DOCUMENT_ROOT}/wp-includes/class-wp-hook.php(348): WP_Hook->apply_filters('', Array)\n` +
	`#7 ${DOCUMENT_ROOT}/wp-includes/plugin.php(565): WP_Hook->do_action(Array)\n` +
	`#8 ${DOCUMENT_ROOT}/wp-includes/class-wp.php(418): do_action_ref_array('parse_request', Array)\n` +
	`#9 ${DOCUMENT_ROOT}/wp-includes/class-wp.php(813): WP->parse_request('')\n` +
	`#10 ${DOCUMENT_ROOT}/wp-includes/functions.php(1336): WP->main('')\n` +
	`#11 ${DOCUMENT_ROOT}/wp-blog-header.php(16): wp()\n` +
	`#12 ${DOCUMENT_ROOT}/index.php(17): require('/var/www/html/w...')\n` +
	'#13 {main}\n' +
	'  thrown';
const CRITICAL_ERROR = {
	code: 'internal_server_error',
	message:
		'<p>There has been a critical error on this website.</p><p><a href="https://wordpress.org/documentation/article/faq-troubleshooting/">Learn more about troubleshooting WordPress.</a></p>',
	data: {
		status: constants.HTTP_STATUS_INTERNAL_SERVER_ERROR,
		error: { type: E_ERROR, message: FATAL_MESSAGE, file: REST_SERVER, line: FATAL_LINE }
	},
	additional_errors: []
};

// What the blog has: its posts (no pages), its authors, and the category every WordPress starts
// with, Uncategorized.
const POST_IDS = new Set(POSTS.map((post) => post.id));
const USER_IDS = new Set(AUTHORS.map((author) => author.id));
const CATEGORY_IDS = new Set([1]);
const POSTS_TYPE = 'posts';
const CATEGORIES_TAXONOMY = 'categories';

// The Allow header WordPress adds to an answer from a matched route (rest_send_allow_header): the
// methods this visitor may use there, which logged out is only reading what exists.
const ALLOW_GET = 'GET';
const ALLOW_POST = 'POST';

interface Answer {
	error: RestError;
	allow: string | null;
}

/** A sub-request that passed the batch's schema. */
interface SubRequest {
	method: string;
	path: string;
}

/**
 * A route a sub-request can match. `answer` gets the method and the route's captures, and returns
 * null if the route doesn't take that method (so the request matches no route at all).
 */
interface Route {
	pattern: RegExp;
	answer: (method: string, captures: string[]) => Answer | null;
}

const CREATE_ERRORS = new Map([
	['posts', CANNOT_CREATE_POST],
	['pages', CANNOT_CREATE_POST],
	['categories', CANNOT_CREATE_TERM],
	['tags', CANNOT_CREATE_TERM],
	['users', CANNOT_CREATE_USER]
]);

/** An item route: it exists or it doesn't, then the visitor may neither change nor delete it. */
function itemAnswer(
	method: string,
	exists: boolean,
	[missing, cannotEdit, cannotDelete]: [RestError, RestError, RestError]
): Answer {
	if (!exists) {
		return { error: missing, allow: null };
	}
	return { error: method === DELETE_METHOD ? cannotDelete : cannotEdit, allow: ALLOW_GET };
}

// The core routes that take POST, PUT, PATCH or DELETE (matched ignoring case, as WordPress does),
// including two that can't be batched.
const ROUTES: Route[] = [
	{
		pattern: /^\/wp\/v2\/(posts|pages|categories|tags|users)$/i,
		answer: (method, [collection = '']) => {
			const error = CREATE_ERRORS.get(collection.toLowerCase());
			return method === DEFAULT_METHOD && error ? { error, allow: ALLOW_GET } : null;
		}
	},
	{
		pattern: /^\/wp\/v2\/(posts|pages)\/(\d+)$/i,
		answer: (method, [type = '', id = '']) =>
			itemAnswer(method, type.toLowerCase() === POSTS_TYPE && POST_IDS.has(Number(id)), [
				INVALID_POST,
				CANNOT_EDIT_POST,
				CANNOT_DELETE_POST
			])
	},
	{
		pattern: /^\/wp\/v2\/(categories|tags)\/(\d+)$/i,
		answer: (method, [taxonomy = '', id = '']) =>
			itemAnswer(
				method,
				taxonomy.toLowerCase() === CATEGORIES_TAXONOMY && CATEGORY_IDS.has(Number(id)),
				[INVALID_TERM, CANNOT_EDIT_TERM, CANNOT_DELETE_TERM]
			)
	},
	{
		pattern: /^\/wp\/v2\/users\/(\d+)$/i,
		answer: (method, [id = '']) =>
			itemAnswer(method, USER_IDS.has(Number(id)), [
				INVALID_USER,
				CANNOT_EDIT_USER,
				CANNOT_DELETE_USER
			])
	},
	{
		pattern: /^\/batch\/v1$/i,
		answer: (method) =>
			method === DEFAULT_METHOD ? { error: BATCH_NOT_ALLOWED, allow: ALLOW_POST } : null
	},
	{
		// Only an editor may render blocks, so nothing is allowed.
		pattern: /^\/wp\/v2\/block-renderer\/[a-z0-9-]+\/[a-z0-9-]+$/i,
		answer: (method) =>
			method === DEFAULT_METHOD ? { error: BATCH_NOT_ALLOWED, allow: null } : null
	}
];

/** match_request_to_handler(), then the allow_batch check. */
function answer(method: string, path: string): Answer {
	for (const route of ROUTES) {
		const match = route.pattern.exec(path);
		if (match) {
			return route.answer(method, match.slice(1)) ?? { error: REST_NO_ROUTE, allow: null };
		}
	}
	return { error: REST_NO_ROUTE, allow: null };
}

/** The errors WordPress finds before running anything, which require-all-validate stops at. */
function isValidationError({ error }: Answer): boolean {
	return error === REST_NO_ROUTE || error === BATCH_NOT_ALLOWED;
}

/** A sub-request's answer, as envelope_response() wraps it. */
function envelope({ error, allow }: Answer) {
	return { body: error, status: errorStatus(error), headers: allow ? { Allow: allow } : [] };
}

/** The path wp_parse_url() finds in a sub-request's; null where PHP's parse_url() fails. */
function parsePath(path: string): string | null {
	try {
		return new URL(path, 'http://localhost').pathname;
	} catch {
		return null;
	}
}

function isObject(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

// wp_sprintf()'s `%l` joins a pair with `and`, more with commas.
const PAIR = 2;

/** wp_sprintf()'s `%l`: `a, b, and c`, or `a and b`. */
function list(values: string[]): string {
	return values.length === PAIR
		? values.join(' and ')
		: `${values.slice(0, -1).join(', ')}, and ${values.at(-1) ?? ''}`;
}

function invalidType(param: string, type: string): RestError {
	return {
		code: 'rest_invalid_type',
		message: `${param} is not of type ${type}.`,
		data: { param }
	};
}

function notInEnum(param: string, values: string[]): RestError {
	return restError('rest_not_in_enum', `${param} is not one of ${list(values)}.`);
}

/** rest_validate_value_from_schema() for one sub-request, `requests[i]`. */
function validateRequest(request: unknown, param: string): SubRequest | RestError {
	if (!isObject(request)) {
		return invalidType(param, SchemaType.OBJECT);
	}
	const path = request[Property.PATH];
	if (path === undefined) {
		return restError(
			'rest_property_required',
			`${Property.PATH} is a required property of ${param}.`
		);
	}
	// Each property as sent, in the order sent.
	for (const [name, value] of Object.entries(request)) {
		const property = `${param}[${name}]`;
		if (name === Property.METHOD && typeof value !== 'string') {
			return invalidType(property, SchemaType.STRING);
		}
		if (name === Property.METHOD && typeof value === 'string' && !BATCH_METHODS.includes(value)) {
			return notInEnum(property, BATCH_METHODS);
		}
		if (name === Property.PATH && typeof value !== 'string') {
			return invalidType(property, SchemaType.STRING);
		}
		if (name === Property.BODY && !isObject(value)) {
			return invalidType(property, SchemaType.OBJECT);
		}
	}
	const method = request[Property.METHOD];
	return {
		method: typeof method === 'string' ? method : DEFAULT_METHOD,
		path: typeof path === 'string' ? path : ''
	};
}

function isRestError(value: SubRequest | RestError): value is RestError {
	return 'code' in value;
}

/** The batch's own parameters, checked as rest_parse_request_arg() does. */
function validateParams(params: Record<string, unknown>): SubRequest[] | RestError {
	const invalid = new Map<string, RestError>();
	const validation = params[Param.VALIDATION];
	if (validation !== undefined && typeof validation !== 'string') {
		invalid.set(Param.VALIDATION, invalidType(Param.VALIDATION, SchemaType.STRING));
	} else if (validation !== undefined && !VALIDATION_MODES.includes(validation)) {
		invalid.set(Param.VALIDATION, notInEnum(Param.VALIDATION, VALIDATION_MODES));
	}
	const requests = params[Param.REQUESTS];
	let checked: SubRequest[] = [];
	if (!Array.isArray(requests)) {
		invalid.set(Param.REQUESTS, invalidType(Param.REQUESTS, SchemaType.ARRAY));
	} else {
		const results = requests.map((request, index) =>
			validateRequest(request, `${Param.REQUESTS}[${String(index)}]`)
		);
		const failed = results.find(isRestError);
		if (failed) {
			invalid.set(Param.REQUESTS, failed);
		} else if (results.length > MAX_BATCH_SIZE) {
			invalid.set(
				Param.REQUESTS,
				restError(
					'rest_too_many_items',
					`${Param.REQUESTS} must contain at most ${String(MAX_BATCH_SIZE)} items.`
				)
			);
		}
		checked = results.filter((result): result is SubRequest => !isRestError(result));
	}
	if (invalid.size === 0) {
		return checked;
	}
	const names = [...invalid.keys()];
	return restError('rest_invalid_param', `Invalid parameter(s): ${names.join(', ')}`, BAD_REQUEST, {
		params: Object.fromEntries([...invalid].map(([name, error]) => [name, error.message])),
		details: Object.fromEntries(invalid)
	});
}

/** The JSON body's parameters, as WordPress reads them: only from a JSON request. */
async function jsonParams(
	request: Request
): Promise<{ params: Record<string, unknown> } | { error: RestError }> {
	const contentType = request.headers.get(CONTENT_TYPE_HEADER) ?? '';
	const body = await request.text();
	if (!contentType.startsWith(JSON_CONTENT_TYPE) || body === '') {
		return { params: {} };
	}
	try {
		const parsed: unknown = JSON.parse(body);
		return { params: isObject(parsed) ? parsed : {} };
	} catch {
		const error = restError('rest_invalid_json', 'Invalid JSON body passed.', BAD_REQUEST, {
			json_error_code: JSON_ERROR_SYNTAX,
			json_error_message: JSON_ERROR_SYNTAX_MESSAGE
		});
		return { error };
	}
}

export interface BatchResult {
	status: number;
	body: unknown;
	headers?: Record<string, string>;
}

/** POST /batch/v1: what WordPress answers it with. */
export async function batch(request: Request): Promise<BatchResult> {
	const parsed = await jsonParams(request);
	if ('error' in parsed) {
		return { status: BAD_REQUEST, body: parsed.error };
	}
	const { params } = parsed;
	if (params[Param.REQUESTS] === undefined || params[Param.REQUESTS] === null) {
		const missing = restError(
			'rest_missing_callback_param',
			`Missing parameter(s): ${Param.REQUESTS}`,
			BAD_REQUEST,
			{ params: [Param.REQUESTS] }
		);
		return { status: BAD_REQUEST, body: missing };
	}
	const requests = validateParams(params);
	if (!Array.isArray(requests)) {
		return { status: BAD_REQUEST, body: requests };
	}
	const paths = requests.map((subRequest) => parsePath(subRequest.path));
	if (paths.includes(null)) {
		return {
			status: constants.HTTP_STATUS_INTERNAL_SERVER_ERROR,
			body: CRITICAL_ERROR,
			headers: NOCACHE_HEADERS
		};
	}
	const answers = requests.map(({ method }, index) => answer(method, paths[index] ?? ''));
	if (params[Param.VALIDATION] === REQUIRE_ALL_VALID && answers.some(isValidationError)) {
		return {
			status: constants.HTTP_STATUS_MULTI_STATUS,
			body: {
				failed: VALIDATION_FAILED,
				responses: answers.map((result) => (isValidationError(result) ? envelope(result) : null))
			}
		};
	}
	return {
		status: constants.HTTP_STATUS_MULTI_STATUS,
		body: { responses: answers.map(envelope) }
	};
}
