import { CONTENT_TYPE_HEADER } from '$lib/server/headers';

// Forms as PHP reads them. PHP fills $_POST only for these content types; any other POST (JSON,
// XML, fields in the query string) looks empty to it. The body is still recorded with the hit, so
// nothing sent another way is lost.
const FORM_CONTENT_TYPES = ['application/x-www-form-urlencoded', 'multipart/form-data'];

/** The posted form, as PHP would see it: null for anything that isn't a form post. */
export async function postedForm(request: Request): Promise<FormData | null> {
	const contentType = request.headers.get(CONTENT_TYPE_HEADER) ?? '';
	if (!FORM_CONTENT_TYPES.some((type) => contentType.startsWith(type))) {
		return null;
	}
	try {
		return await request.formData();
	} catch {
		// A malformed form: PHP ignores what it can't parse.
		return null;
	}
}

/** A submitted text field, or null if it is missing or a file (PHP's `isset( $_POST[...] )`). */
export function field(form: FormData | null, name: string): string | null {
	const value = form?.get(name);
	return typeof value === 'string' ? value : null;
}
