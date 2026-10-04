import {
	autocompletion,
	insertCompletionText,
	startCompletion,
	type Completion,
	type CompletionContext,
	type CompletionResult
} from '@codemirror/autocomplete';
import { EditorState, type ChangeSpec } from '@codemirror/state';
import { EditorView, keymap, placeholder } from '@codemirror/view';
import type { SearchFieldHelp } from '$lib/client';
import { picoEditorTheme, prefersDark } from '$lib/editor-theme';

// The exhibit's search box: a one-line CodeMirror editor that completes the API's search fields
// (search.py), then the values of those that have few. It enhances an <input>, which stays the
// form's field and works without JavaScript; the editor only keeps it up to date. The page loads
// this module with import(), once it runs, so the exhibit's first load doesn't wait for it.

// The field being typed, at the start of a term (after an optional `-`).
const FIELD = /(?:^|\s)-?([a-z_]*)$/;
// A value being typed: the term's field, and the text after its last comma.
const VALUE = /(?:^|\s)-?([a-z_]+):(?:[^\s,"]*,)*([^\s,"]*)$/;
const VALUE_TEXT = /^[^\s,"]*$/;
const FIELD_TEXT = /^[a-z_]*$/;
const SEPARATOR = ':';
const LINE_BREAK = ' ';

/** Completes a field, then offers its values. */
function applyField(view: EditorView, completion: Completion, from: number, to: number): void {
	view.dispatch(insertCompletionText(view.state, completion.label, from, to));
	startCompletion(view);
}

function completions(fields: readonly SearchFieldHelp[]) {
	const fieldOptions: Completion[] = fields.map(({ name, description }) => ({
		label: `${name}${SEPARATOR}`,
		info: description,
		type: 'property',
		apply: applyField
	}));
	const valueOptions = new Map<string, Completion[]>(
		fields.map(({ name, values }) => [
			name,
			values.map((value) => ({ label: value, type: 'enum' }))
		])
	);
	return (context: CompletionContext): CompletionResult | null => {
		const before = context.state.sliceDoc(0, context.pos);
		const value = VALUE.exec(before);
		if (value) {
			const [, name = '', typed = ''] = value;
			const options = valueOptions.get(name) ?? [];
			return options.length === 0
				? null
				: { from: context.pos - typed.length, options, validFor: VALUE_TEXT };
		}
		const field = FIELD.exec(before);
		if (!field) return null;
		const typed = field[1] ?? '';
		if (typed === '' && !context.explicit) return null;
		return { from: context.pos - typed.length, options: fieldOptions, validFor: FIELD_TEXT };
	};
}

// The search is one line: a pasted line break becomes a space, which separates terms just as well.
const oneLine = EditorState.transactionFilter.of((transaction) => {
	if (!transaction.docChanged || transaction.newDoc.lines === 1) return transaction;
	const breaks: ChangeSpec[] = [];
	for (let number = 1; number < transaction.newDoc.lines; number++) {
		const end = transaction.newDoc.line(number).to;
		breaks.push({ from: end, to: end + 1, insert: LINE_BREAK });
	}
	return [transaction, { changes: breaks, sequential: true }];
});

const theme = EditorView.theme({
	'.cm-content': { padding: 'var(--pico-form-element-spacing-vertical) 0' },
	'.cm-line': { padding: '0 var(--pico-form-element-spacing-horizontal)' },
	// Its text area takes the <input>'s aria-invalid (below), as Pico marks an invalid input.
	'&:has(.cm-content[aria-invalid="true"])': { borderColor: 'var(--pico-del-color)' }
});

export interface SearchEditor {
	destroy(): void;
}

// The <input>'s attributes the editor's text area takes over, for assistive technology.
const ARIA = ['aria-label', 'aria-describedby', 'aria-invalid'] as const;

/** Puts a search editor in place of `input`, which it keeps in sync and hides. Enter submits the
 * input's form, unless a completion is open, when it picks the completion. */
export function createSearchEditor(
	input: HTMLInputElement,
	fields: readonly SearchFieldHelp[]
): SearchEditor {
	const aria = Object.fromEntries(
		ARIA.flatMap((name) => {
			const value = input.getAttribute(name);
			return value === null ? [] : [[name, value]];
		})
	);
	const view = new EditorView({
		doc: input.value,
		extensions: [
			picoEditorTheme(prefersDark()),
			theme,
			oneLine,
			placeholder(input.placeholder),
			autocompletion({ override: [completions(fields)], icons: false }),
			keymap.of([
				{
					key: 'Enter',
					run: () => {
						input.form?.requestSubmit();
						return true;
					}
				}
			]),
			EditorView.contentAttributes.of({ ...aria, spellcheck: 'false', autocorrect: 'off' }),
			EditorView.updateListener.of((update) => {
				if (update.docChanged) {
					input.value = update.state.doc.toString();
				}
			})
		]
	});
	input.after(view.dom);
	input.hidden = true;
	return {
		destroy: () => {
			view.destroy();
			input.hidden = false;
		}
	};
}
