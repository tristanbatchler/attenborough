<script lang="ts">
	import { resolve } from '$app/paths';
	import { ADMIN_PATH, LoginError, PASSWORD_FIELD, SITE_NAME, USERNAME_FIELD } from './site';

	// `error` is why the last attempt failed; null on a fresh page.
	let { username, error }: { username: string; error: LoginError | null } = $props();

	const loginPath = resolve('/wp-login.php');
</script>

<!-- Modelled on WordPress 6's login page (wp-login.php). Rendered by $lib/server/html: the CSS is a
     plain <style> in the head, never a component <style>. -->
<svelte:head>
	<meta name="viewport" content="width=device-width, initial-scale=1.0" />
	<title>Log In &lsaquo; {SITE_NAME} &#8212; WordPress</title>
	<meta name="robots" content="max-image-preview:large, noindex, noarchive" />
	<meta name="referrer" content="strict-origin-when-cross-origin" />
	<style>
		html,
		body {
			background: #f0f0f1;
		}
		body {
			margin: 0;
			color: #3c434a;
			font-family:
				-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen-Sans, Ubuntu, Cantarell,
				'Helvetica Neue', sans-serif;
			font-size: 13px;
			line-height: 1.4;
		}
		#login {
			width: 320px;
			padding: 5% 0 0;
			margin: auto;
		}
		#login h1 a {
			display: block;
			width: 84px;
			height: 84px;
			margin: 0 auto 25px;
			border-radius: 50%;
			background: #3c434a;
			text-indent: -9999px;
			overflow: hidden;
		}
		#loginform {
			margin-top: 20px;
			padding: 26px 24px;
			background: #fff;
			border: 1px solid #c3c4c7;
			box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
			overflow: hidden;
		}
		#loginform label {
			display: inline-block;
			margin-bottom: 3px;
			font-size: 14px;
			line-height: 1.5;
		}
		#loginform .input {
			box-sizing: border-box;
			width: 100%;
			min-height: 40px;
			margin: 0 6px 16px 0;
			padding: 0 8px;
			border: 1px solid #8c8f94;
			border-radius: 4px;
			font-size: 24px;
			line-height: 1.33;
		}
		#loginform .forgetmenot {
			float: left;
			margin: 0;
		}
		#loginform .submit {
			float: right;
			margin: 0;
		}
		#wp-submit {
			min-height: 32px;
			padding: 0 12px;
			border: 1px solid #2271b1;
			border-radius: 3px;
			background: #2271b1;
			color: #fff;
			font-size: 13px;
			cursor: pointer;
		}
		#login_error {
			margin-bottom: 20px;
			padding: 12px;
			border-left: 4px solid #d63638;
			background: #fff;
			box-shadow: 0 1px 1px rgba(0, 0, 0, 0.04);
		}
		#nav {
			margin: 24px 0 0;
			padding: 0 24px;
		}
		#nav a {
			color: #50575e;
			text-decoration: none;
		}
	</style>
</svelte:head>

<div id="login">
	<h1><a href="https://wordpress.org/">Powered by WordPress</a></h1>

	{#if error}
		<div id="login_error" class="notice notice-error">
			<p>
				<strong>Error:</strong>
				{#if error === LoginError.EMPTY_USERNAME}
					The username field is empty.
				{:else if error === LoginError.EMPTY_PASSWORD}
					The password field is empty.
				{:else}
					The username <strong>{username}</strong> is not registered on this site. If you are unsure of
					your username, try your email address instead.
				{/if}
			</p>
		</div>
	{/if}

	<form name="loginform" id="loginform" action={loginPath} method="post">
		<p>
			<label for="user_login">Username or Email Address</label>
			<input
				type="text"
				name={USERNAME_FIELD}
				id="user_login"
				class="input"
				value={username}
				size="20"
				autocapitalize="off"
				autocomplete="username"
				required
			/>
		</p>
		<div class="user-pass-wrap">
			<label for="user_pass">Password</label>
			<div class="wp-pwd">
				<input
					type="password"
					name={PASSWORD_FIELD}
					id="user_pass"
					class="input password-input"
					value=""
					size="20"
					autocomplete="current-password"
					spellcheck="false"
					required
				/>
			</div>
		</div>
		<p class="forgetmenot">
			<input name="rememberme" type="checkbox" id="rememberme" value="forever" />
			<label for="rememberme">Remember Me</label>
		</p>
		<p class="submit">
			<input
				type="submit"
				name="wp-submit"
				id="wp-submit"
				class="button button-primary button-large"
				value="Log In"
			/>
			<input type="hidden" name="redirect_to" value={ADMIN_PATH} />
			<input type="hidden" name="testcookie" value="1" />
		</p>
	</form>

	<p id="nav">
		<a href={resolve('/wp-login.php?action=lostpassword')}>Lost your password?</a>
	</p>
</div>
