import { html } from '@codemirror/lang-html';
import { json } from '@codemirror/lang-json';
import { liquid } from '@codemirror/lang-liquid';
import { syntaxHighlighting } from '@codemirror/language';
import { Compartment } from '@codemirror/state';
import { oneDarkHighlightStyle } from '@codemirror/theme-one-dark';
import { basicSetup, EditorView } from 'codemirror';
import type { Marker } from '$lib/client';
import { picoEditorTheme, prefersDark } from '$lib/editor-theme';

// A code editor for a response rule's body: CodeMirror 6 with Liquid over HTML or JSON, completing
// the API's markers. It enhances a <textarea>, which stays the form's field and works without
// JavaScript; the editor only keeps it up to date. Admin pages only: nothing public loads it.

export type EditorMode = 'html' | 'json' | 'text';

const HTML_TYPE = /html/i;
const JSON_TYPE = /json/i;
const VARIABLE = 'variable';

/** The language to highlight a body of `contentType` as. */
export function editorMode(contentType: string): EditorMode {
	if (HTML_TYPE.test(contentType)) return 'html';
	if (JSON_TYPE.test(contentType)) return 'json';
	return 'text';
}

const theme = EditorView.theme({
	'.cm-scroller': { minHeight: '12em', maxHeight: '36em' },
	'.cm-gutters': {
		backgroundColor: 'transparent',
		color: 'var(--pico-muted-color)',
		border: 'none'
	},
	'.cm-activeLine, .cm-activeLineGutter': { backgroundColor: 'var(--pico-muted-border-color)' }
});

export interface Editor {
	setMode(mode: EditorMode): void;
	destroy(): void;
}

/** Puts an editor in place of `textarea`, which it keeps in sync and hides. */
export function createEditor(
	textarea: HTMLTextAreaElement,
	mode: EditorMode,
	markers: readonly Marker[]
): Editor {
	const variables = markers.map(({ name, description }) => ({
		label: name,
		info: description,
		type: VARIABLE
	}));
	const language = (editing: EditorMode) =>
		liquid({
			variables,
			...(editing === 'html' ? { base: html() } : editing === 'json' ? { base: json() } : {})
		});
	const languageSlot = new Compartment();
	const dark = prefersDark();
	const view = new EditorView({
		doc: textarea.value,
		extensions: [
			basicSetup,
			picoEditorTheme(dark),
			theme,
			// basicSetup's default style, meant for light backgrounds, only applies when no other does.
			...(dark ? [syntaxHighlighting(oneDarkHighlightStyle)] : []),
			EditorView.lineWrapping,
			languageSlot.of(language(mode)),
			EditorView.updateListener.of((update) => {
				if (update.docChanged) {
					textarea.value = update.state.doc.toString();
				}
			})
		]
	});
	textarea.after(view.dom);
	textarea.hidden = true;
	return {
		setMode: (next) => {
			view.dispatch({ effects: languageSlot.reconfigure(language(next)) });
		},
		destroy: () => {
			view.destroy();
			textarea.hidden = false;
		}
	};
}
