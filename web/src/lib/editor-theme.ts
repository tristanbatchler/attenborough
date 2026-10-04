import { EditorView } from '@codemirror/view';

// What every CodeMirror editor in the exhibit looks like: a Pico form field, in the reader's colour
// scheme, as Pico follows it. Its own module, so the public search box (search-editor.ts) doesn't
// load the rule editor's languages.

const DARK_SCHEME = '(prefers-color-scheme: dark)';
const TEXT_COLOR = 'var(--pico-color)';

/** Whether the reader's colour scheme is dark, as Pico sees it. */
export function prefersDark(): boolean {
	return window.matchMedia(DARK_SCHEME).matches;
}

/** A Pico form field's look. Each kind of editor adds its own rules as another theme. */
export const picoEditorTheme = (dark: boolean) =>
	EditorView.theme(
		{
			'&': {
				backgroundColor: 'var(--pico-form-element-background-color)',
				color: TEXT_COLOR,
				border: 'var(--pico-border-width) solid var(--pico-form-element-border-color)',
				borderRadius: 'var(--pico-border-radius)',
				marginBottom: 'var(--pico-spacing)'
			},
			'&.cm-focused': { outline: 'var(--pico-outline-width) solid var(--pico-primary-focus)' },
			'.cm-scroller': { fontFamily: 'var(--pico-font-family-monospace)' },
			'.cm-content': { caretColor: TEXT_COLOR },
			'.cm-tooltip': {
				backgroundColor: 'var(--pico-card-background-color)',
				color: TEXT_COLOR,
				border: 'var(--pico-border-width) solid var(--pico-muted-border-color)'
			}
		},
		{ dark }
	);
