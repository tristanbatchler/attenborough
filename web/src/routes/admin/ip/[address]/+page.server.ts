import { fail } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { banIp, listIpBans, revokeBan } from '$lib/client';
import { DURATIONS, BAN_ID_FIELD, expiryAfter, DURATION_FIELD, REASON_FIELD } from '$lib/admin';
import { adminOptions, textField, unwrapAdmin } from '$lib/server/admin';
import type { Actions, PageServerLoad } from './$types';

const INVALID_INPUT = 'That is not a valid IP address.';

export const load: PageServerLoad = async ({ params, fetch, cookies }) => ({
	address: params.address,
	bans: unwrapAdmin(
		await listIpBans({ ...adminOptions(fetch, cookies), path: { ip_addr: params.address } }),
		INVALID_INPUT
	)
});

export const actions = {
	ban: async ({ params, request, fetch, cookies }) => {
		const form = await request.formData();
		const duration = DURATIONS.find(({ value }) => value === form.get(DURATION_FIELD));
		if (duration === undefined) {
			return fail(constants.HTTP_STATUS_BAD_REQUEST, { message: 'Choose how long the ban lasts.' });
		}
		const result = await banIp({
			...adminOptions(fetch, cookies),
			path: { ip_addr: params.address },
			body: { reason: textField(form, REASON_FIELD), expires: expiryAfter(duration) }
		});
		if (result.response?.status === constants.HTTP_STATUS_CONFLICT) {
			return fail(constants.HTTP_STATUS_CONFLICT, { message: 'This address is already banned.' });
		}
		unwrapAdmin(result, INVALID_INPUT);
		return;
	},
	revoke: async ({ request, fetch, cookies }) => {
		const form = await request.formData();
		const banId = Number(form.get(BAN_ID_FIELD));
		if (!Number.isSafeInteger(banId)) {
			return fail(constants.HTTP_STATUS_BAD_REQUEST, { message: 'No such ban.' });
		}
		const result = await revokeBan({
			...adminOptions(fetch, cookies),
			path: { ban_id: banId },
			body: { reason: textField(form, REASON_FIELD) }
		});
		if (result.response?.status === constants.HTTP_STATUS_NOT_FOUND) {
			// No active ban with that id (it expired, or was revoked already), or not an admin: the
			// page's reload tells the two apart.
			return fail(constants.HTTP_STATUS_NOT_FOUND, { message: 'That ban is no longer active.' });
		}
		unwrapAdmin(result);
		return;
	}
} satisfies Actions;
