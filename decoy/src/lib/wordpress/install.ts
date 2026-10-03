// What the installer page (InstallPage.svelte) shows, decided by $lib/server/install.

/** Why install.php refused a submission; each has its own message. */
export const InstallError = {
	NO_USERNAME: 'no_username',
	INVALID_USERNAME: 'invalid_username',
	PASSWORD_MISMATCH: 'password_mismatch',
	NO_EMAIL: 'no_email',
	INVALID_EMAIL: 'invalid_email'
} as const;
export type InstallError = (typeof InstallError)[keyof typeof InstallError];

/** What the setup form's "Discourage search engines" checkbox sends: blog_public 0. */
export const DISCOURAGE_SEARCH_ENGINES = '0';

/** The setup form's values: what was submitted, as WordPress puts it back. */
export interface SetupForm {
	siteTitle: string;
	username: string;
	email: string;
	/** The password field's suggestion: the one submitted, or a fresh random one. */
	initialPassword: string;
	passwordSubmitted: boolean;
	discourageSearchEngines: boolean;
	language: string;
}

export type InstallScreen =
	| { kind: 'welcome'; form: SetupForm }
	| { kind: 'error'; error: InstallError; form: SetupForm }
	| { kind: 'success'; username: string; generatedPassword: string | null }
	/** A step install.php has no case for: the header and nothing else. */
	| { kind: 'blank' };
