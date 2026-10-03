import { getRule, listRuleMarkers } from '$lib/client';
import { adminOptions, unwrapAdmin } from '$lib/server/admin';
import { defaultPreview, ruleActions, ruleValues } from '$lib/server/rules';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params, fetch, cookies }) => {
	const options = adminOptions(fetch, cookies);
	const [rule, markers] = await Promise.all([
		getRule({ ...options, path: { rule_id: Number(params.id) } }),
		listRuleMarkers(options)
	]);
	const saved = unwrapAdmin(rule);
	return {
		rule: saved,
		values: ruleValues(saved, true),
		previewInput: defaultPreview(),
		markers: unwrapAdmin(markers)
	};
};

export const actions = ruleActions(({ id }) => Number(id));
