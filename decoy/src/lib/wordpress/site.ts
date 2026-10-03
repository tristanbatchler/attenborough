// The WordPress install the decoy imitates: names shared by its pages and their server code. The
// blog it hosts (name, posts, authors) is $lib/site/blog.

/** WordPress's login form fields. */
export const USERNAME_FIELD = 'log';
export const PASSWORD_FIELD = 'pwd';

/** The login page. */
export const LOGIN_PATH = '/wp-login.php';

/** Where WordPress sends a successful login. */
export const ADMIN_PATH = '/wp-admin/';

/** WordPress's own codes for why a login failed; each has its own message on the login page. */
export const LoginError = {
	EMPTY_USERNAME: 'empty_username',
	EMPTY_PASSWORD: 'empty_password',
	INVALID_USERNAME: 'invalid_username'
} as const;
export type LoginError = (typeof LoginError)[keyof typeof LoginError];
