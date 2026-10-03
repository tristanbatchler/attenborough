import { listRuleMarkers } from '$lib/client';
import { ADDRESS_PARAM, EXAMPLE_PARAM } from '$lib/params';
import { RULE_EXAMPLES } from '$lib/rule-examples';
import { adminOptions, unwrapAdmin } from '$lib/server/admin';
import { defaultPreview, ruleActions, ruleValues } from '$lib/server/rules';
import type { PageServerLoad } from './$types';

// A new rule: blank, from an example (?example=), or for one address (?address=, from its admin page).
export const load: PageServerLoad = async ({ url, fetch, cookies }) => {
	const example = RULE_EXAMPLES.find(({ slug }) => slug === url.searchParams.get(EXAMPLE_PARAM));
	const given = url.searchParams.get(ADDRESS_PARAM)?.trim();
	const address = given === '' ? undefined : given;
	const values = ruleValues(example?.rule ?? {}, false);
	if (address !== undefined && values.condition === '') {
		values.condition = `ip == ${JSON.stringify(address)}`;
	}
	return {
		values,
		previewInput: defaultPreview(address),
		markers: unwrapAdmin(await listRuleMarkers(adminOptions(fetch, cookies)))
	};
};

export const actions = ruleActions(() => undefined);
