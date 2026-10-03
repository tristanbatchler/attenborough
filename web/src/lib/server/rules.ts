import { fail, redirect, type Actions } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { resolve } from '$app/paths';
import {
	createRule,
	previewRule,
	updateRule,
	type HttpValidationError,
	type Preview,
	type RuleForm
} from '$lib/client';
import {
	DURATIONS,
	expiryAfter,
	HTTP_METHODS,
	KEEP_EXPIRY,
	NO_END,
	RULE_FIELDS,
	type PreviewInput,
	type RuleValues
} from '$lib/admin';
import { adminOptions, unwrapAdmin } from '$lib/server/admin';

// The response rule form (RuleForm.svelte) as text, and its save and preview actions, shared by the
// new rule and edit rule pages. The API checks and renders every rule; this only turns the form's
// text into the API's shape and back.

const HEADER_SEPARATOR = ':';
const NEWLINE = '\n';
const LINE_BREAK = /\r?\n/;
const DEFAULT_PREVIEW_IP = '203.0.113.7';
const DEFAULT_PREVIEW_METHOD = HTTP_METHODS[0];
const DEFAULT_PREVIEW_PATH = '/';
// pydantic's prefix on a validator's message.
const VALUE_ERROR_PREFIX = 'Value error, ';
const NOT_A_NUMBER = 'The status and the delay must be whole numbers.';

/** The form's text for a rule, saved or not (an example). */
export function ruleValues(rule: RuleForm, isSaved: boolean): RuleValues {
	return {
		method: rule.method ?? '',
		pathPattern: rule.path_pattern ?? '',
		condition: rule.condition ?? '',
		statusCode: String(rule.status_code ?? constants.HTTP_STATUS_OK),
		contentType: rule.content_type ?? '',
		headers: Object.entries(rule.headers ?? {})
			.map(([name, value]) => `${name}${HEADER_SEPARATOR} ${value}`)
			.join(NEWLINE),
		body: rule.body ?? '',
		delayMs: String(rule.delay_ms ?? 0),
		duration: isSaved ? KEEP_EXPIRY : NO_END,
		currentExpiry: rule.expires ?? '',
		note: rule.note ?? ''
	};
}

function text(form: FormData, name: string): string {
	const value = form.get(name);
	return typeof value === 'string' ? value : '';
}

function valuesFromForm(form: FormData): RuleValues {
	return {
		method: text(form, RULE_FIELDS.method),
		pathPattern: text(form, RULE_FIELDS.pathPattern),
		condition: text(form, RULE_FIELDS.condition),
		statusCode: text(form, RULE_FIELDS.statusCode),
		contentType: text(form, RULE_FIELDS.contentType),
		headers: text(form, RULE_FIELDS.headers),
		body: text(form, RULE_FIELDS.body),
		delayMs: text(form, RULE_FIELDS.delayMs),
		duration: text(form, RULE_FIELDS.duration),
		currentExpiry: text(form, RULE_FIELDS.currentExpiry),
		note: text(form, RULE_FIELDS.note)
	};
}

export function defaultPreview(ip?: string): PreviewInput {
	return {
		ip: ip ?? DEFAULT_PREVIEW_IP,
		method: DEFAULT_PREVIEW_METHOD,
		path: DEFAULT_PREVIEW_PATH
	};
}

function previewFromForm(form: FormData): PreviewInput {
	return {
		ip: text(form, RULE_FIELDS.previewIp).trim(),
		method: text(form, RULE_FIELDS.previewMethod).trim(),
		path: text(form, RULE_FIELDS.previewPath)
	};
}

/** The API's shape of the form, or what is wrong with it before the API need look. */
function ruleFromValues(values: RuleValues): RuleForm | string {
	const statusCode = Number(values.statusCode);
	const delayMs = Number(values.delayMs || '0');
	if (!Number.isSafeInteger(statusCode) || !Number.isSafeInteger(delayMs)) {
		return NOT_A_NUMBER;
	}
	const headers: Record<string, string> = {};
	for (const line of values.headers.split(LINE_BREAK)) {
		if (line.trim() === '') continue;
		const separator = line.indexOf(HEADER_SEPARATOR);
		if (separator < 1) {
			return `"${line}" is not a header: write one "Name: value" per line.`;
		}
		headers[line.slice(0, separator).trim()] = line.slice(separator + 1).trim();
	}
	let expires: string | null;
	if (values.duration === KEEP_EXPIRY) {
		expires = values.currentExpiry || null;
	} else {
		const duration = DURATIONS.find(({ value }) => value === values.duration);
		if (duration === undefined) return 'Choose how long the rule lasts.';
		expires = expiryAfter(duration);
	}
	return {
		method: values.method || null,
		path_pattern: values.pathPattern || null,
		condition: values.condition,
		status_code: statusCode,
		content_type: values.contentType,
		headers,
		body: values.body,
		delay_ms: delayMs,
		expires,
		note: values.note || null
	};
}

/** The API's reasons for refusing a rule (422), as one message: Liquid's, with the line. */
function refusal(error: HttpValidationError): string {
	return (error.detail ?? [])
		.map(({ msg }) =>
			msg.startsWith(VALUE_ERROR_PREFIX) ? msg.slice(VALUE_ERROR_PREFIX.length) : msg
		)
		.join(NEWLINE);
}

interface RuleFailure {
	values: RuleValues;
	previewInput: PreviewInput;
	message: string;
}

function refused(values: RuleValues, previewInput: PreviewInput, message: string) {
	return fail(constants.HTTP_STATUS_BAD_REQUEST, {
		values,
		previewInput,
		message
	} satisfies RuleFailure);
}

/**
 * The save and preview actions, for a new rule or a saved one: `savedRule` reads the saved rule's
 * id from the route's parameters, and gives undefined for a new rule.
 */
export function ruleActions(
	savedRule: (params: Partial<Record<string, string>>) => number | undefined
) {
	return {
		save: async ({ request, fetch, cookies, params }) => {
			const ruleId = savedRule(params);
			const form = await request.formData();
			const values = valuesFromForm(form);
			const previewInput = previewFromForm(form);
			const rule = ruleFromValues(values);
			if (typeof rule === 'string') return refused(values, previewInput, rule);
			const options = adminOptions(fetch, cookies);
			if (ruleId === undefined) {
				const created = await createRule({ ...options, body: rule });
				if (
					created.error &&
					created.response?.status === constants.HTTP_STATUS_UNPROCESSABLE_ENTITY
				) {
					return refused(values, previewInput, refusal(created.error));
				}
				const { id } = unwrapAdmin(created);
				redirect(
					constants.HTTP_STATUS_SEE_OTHER,
					resolve('/admin/rules/[id=id]', { id: String(id) })
				);
			}
			const updated = await updateRule({ ...options, path: { rule_id: ruleId }, body: rule });
			if (
				updated.error &&
				updated.response?.status === constants.HTTP_STATUS_UNPROCESSABLE_ENTITY
			) {
				return refused(values, previewInput, refusal(updated.error));
			}
			unwrapAdmin(updated);
			redirect(constants.HTTP_STATUS_SEE_OTHER, resolve('/admin/rules'));
		},
		preview: async ({ request, fetch, cookies }) => {
			const form = await request.formData();
			const values = valuesFromForm(form);
			const previewInput = previewFromForm(form);
			const rule = ruleFromValues(values);
			if (typeof rule === 'string') return refused(values, previewInput, rule);
			const result = await previewRule({
				...adminOptions(fetch, cookies),
				body: { rule, ip: previewInput.ip, method: previewInput.method, path: previewInput.path }
			});
			if (result.error && result.response?.status === constants.HTTP_STATUS_UNPROCESSABLE_ENTITY) {
				return refused(values, previewInput, refusal(result.error));
			}
			const preview: Preview = unwrapAdmin(result);
			return { values, previewInput, preview };
		}
	} satisfies Actions;
}
