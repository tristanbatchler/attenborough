import { fail } from '@sveltejs/kit';
import { constants } from 'node:http2';
import { listRules, moveRule, removeRule, type Direction } from '$lib/client';
import { RULE_FIELDS } from '$lib/admin';
import { adminOptions, unwrapAdmin } from '$lib/server/admin';
import type { Actions, PageServerLoad } from './$types';

const DIRECTIONS: readonly Direction[] = ['up', 'down'];

export const load: PageServerLoad = async ({ fetch, cookies }) => ({
	rules: unwrapAdmin(await listRules(adminOptions(fetch, cookies)))
});

function ruleId(form: FormData): number | undefined {
	const id = Number(form.get(RULE_FIELDS.ruleId));
	return Number.isSafeInteger(id) ? id : undefined;
}

export const actions = {
	move: async ({ request, fetch, cookies }) => {
		const form = await request.formData();
		const id = ruleId(form);
		const direction = DIRECTIONS.find((d) => d === form.get(RULE_FIELDS.direction));
		if (id === undefined || direction === undefined) {
			return fail(constants.HTTP_STATUS_BAD_REQUEST, { message: 'No such rule.' });
		}
		unwrapAdmin(
			await moveRule({
				...adminOptions(fetch, cookies),
				path: { rule_id: id },
				body: { direction }
			})
		);
		return;
	},
	remove: async ({ request, fetch, cookies }) => {
		const id = ruleId(await request.formData());
		if (id === undefined) {
			return fail(constants.HTTP_STATUS_BAD_REQUEST, { message: 'No such rule.' });
		}
		unwrapAdmin(await removeRule({ ...adminOptions(fetch, cookies), path: { rule_id: id } }));
		return;
	}
} satisfies Actions;
