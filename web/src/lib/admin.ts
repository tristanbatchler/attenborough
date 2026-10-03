// The admin area's forms: their fields, shared by the pages and their actions, and how long a ban or
// a rule lasts. Durations rather than a date, so there is no time zone to get wrong.
export const DURATION_FIELD = 'duration';
export const REASON_FIELD = 'reason';
export const BAN_ID_FIELD = 'ban_id';

/** The response rule form's fields (RuleForm, and the rules list's buttons). */
export const RULE_FIELDS = {
	ruleId: 'rule_id',
	method: 'method',
	pathPattern: 'path_pattern',
	condition: 'condition',
	statusCode: 'status_code',
	contentType: 'content_type',
	headers: 'headers',
	body: 'body',
	delayMs: 'delay_ms',
	duration: DURATION_FIELD,
	currentExpiry: 'current_expiry',
	note: 'note',
	direction: 'direction',
	previewIp: 'preview_ip',
	previewMethod: 'preview_method',
	previewPath: 'preview_path'
} as const;

/** Every field of the form, as the text it shows. */
export interface RuleValues {
	method: string;
	pathPattern: string;
	condition: string;
	statusCode: string;
	contentType: string;
	/** One `Name: value` per line. */
	headers: string;
	body: string;
	delayMs: string;
	duration: string;
	/** The saved rule's expiry (ISO 8601), kept when the duration is KEEP_EXPIRY; '' for none. */
	currentExpiry: string;
	note: string;
}

/** The request a preview tries the rule on. */
export interface PreviewInput {
	ip: string;
	method: string;
	path: string;
}

/** The duration that keeps an edited rule's expiry as it was. */
export const KEEP_EXPIRY = 'keep';

const MS_PER_HOUR = 3_600_000;

/** The duration with no end. */
export const NO_END = 'forever';

/** The methods a rule's form offers (blank: any). */
export const HTTP_METHODS = ['GET', 'POST', 'HEAD', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'] as const;

export const DURATIONS = [
	{ value: '1h', label: '1 hour', hours: 1 },
	{ value: '1d', label: '1 day', hours: 24 },
	{ value: '7d', label: '1 week', hours: 168 },
	{ value: '30d', label: '30 days', hours: 720 },
	{ value: NO_END, label: 'Until removed', hours: null }
] as const;

export type Duration = (typeof DURATIONS)[number];

/** When something lasting `duration` from now ends, as ISO 8601; null for never. */
export function expiryAfter(duration: Duration): string | null {
	return duration.hours === null
		? null
		: new Date(Date.now() + duration.hours * MS_PER_HOUR).toISOString();
}
