import { constants } from 'node:http2';

// The REST API's errors, as WordPress serialises a WP_Error (rest_convert_error_to_response):
// `data` is whatever the error carried, null when nothing.

export interface RestError {
	code: string;
	message: string;
	data: Record<string, unknown> | null;
}

export function restError(
	code: string,
	message: string,
	status?: number,
	extra: Record<string, unknown> = {}
): RestError {
	return { code, message, data: status === undefined ? null : { status, ...extra } };
}

/** The status a WP_Error is answered with: its own, or 500 when it has none. */
export function errorStatus(error: RestError): number {
	const status = error.data?.['status'];
	return typeof status === 'number' ? status : constants.HTTP_STATUS_INTERNAL_SERVER_ERROR;
}

export const REST_NO_ROUTE = restError(
	'rest_no_route',
	'No route was found matching the URL and request method.',
	constants.HTTP_STATUS_NOT_FOUND
);
