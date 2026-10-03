<script lang="ts">
	import { resolve } from '$app/paths';
	import { DISCOURAGE_SEARCH_ENGINES, InstallError, type InstallScreen } from './install';

	let { screen }: { screen: InstallScreen } = $props();
</script>

<!-- Modelled on WordPress 6.6.2's wp-admin/install.php: display_header(), display_setup_form() and
     the steps' own markup. Its stylesheet is inlined (the decoy serves no wp-admin/css), and the
     jQuery it prints at the end is left out. Rendered by $lib/server/html: the CSS is a plain
     <style> in the head, never a component <style>. -->
<svelte:head>
	<meta name="viewport" content="width=device-width" />
	<meta http-equiv="content-type" content="text/html; charset=utf-8" />
	<meta name="robots" content="noindex,nofollow" />
	<title>WordPress &rsaquo; Installation</title>
	<style>
		html {
			background: #f0f0f1;
			margin: 0 20px;
		}
		body {
			background: #fff;
			border: 1px solid #c3c4c7;
			color: #3c434a;
			font-family:
				-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen-Sans, Ubuntu, Cantarell,
				'Helvetica Neue', sans-serif;
			margin: 140px auto 25px;
			padding: 20px 20px 10px;
			max-width: 700px;
			box-shadow: 0 1px 1px rgba(0, 0, 0, 0.04);
		}
		h1 {
			border-bottom: 1px solid #dcdcde;
			clear: both;
			color: #646970;
			font-size: 24px;
			margin: 30px 0;
			padding: 0 0 7px;
			font-weight: 400;
		}
		h2 {
			font-size: 16px;
		}
		p,
		li,
		dd,
		dt {
			padding-bottom: 2px;
			font-size: 14px;
			line-height: 1.5;
		}
		code,
		.code {
			font-family: Consolas, Monaco, monospace;
		}
		#logo {
			margin: -130px auto 25px;
			padding: 0 0 25px;
			width: 84px;
			height: 84px;
			overflow: hidden;
			text-indent: -9999px;
			background: #3c434a;
			border-radius: 50%;
		}
		.message {
			border-left: 4px solid #d63638;
			padding: 0.7em 0.6em;
			background-color: #fcf0f1;
		}
		.form-table {
			border-collapse: collapse;
			margin-top: 1em;
			width: 100%;
		}
		.form-table td,
		.form-table th {
			margin-bottom: 9px;
			padding: 10px 20px 10px 0;
			font-size: 14px;
			vertical-align: top;
			text-align: left;
		}
		.form-table th {
			width: 140px;
		}
		.form-table input[type='text'],
		.form-table input[type='email'],
		.form-table input[type='password'] {
			width: 218px;
			line-height: 2;
			font-size: 15px;
			padding: 3px 5px;
		}
		.form-table p {
			margin: 4px 0 0;
			font-size: 11px;
		}
		.description {
			color: #646970;
		}
		.step {
			margin: 20px 0 15px;
		}
		.step .button-large {
			font-size: 14px;
		}
		.button {
			display: inline-block;
			min-height: 32px;
			padding: 0 12px;
			border: 1px solid #2271b1;
			border-radius: 3px;
			background: #f6f7f7;
			color: #2271b1;
			font-size: 13px;
			line-height: 2.3;
			text-decoration: none;
			cursor: pointer;
		}
		.hide-if-no-js {
			display: none;
		}
	</style>
</svelte:head>

<p id="logo">WordPress</p>

{#if screen.kind === 'welcome'}
	<h1>Welcome</h1>
	<p>
		Welcome to the famous five-minute WordPress installation process! Just fill in the information
		below and you&#8217;ll be on your way to using the most extendable and powerful personal
		publishing platform in the world.
	</p>

	<h2>Information needed</h2>
	<p>
		Please provide the following information. Do not worry, you can always change these settings
		later.
	</p>
{:else if screen.kind === 'error'}
	<h1>Welcome</h1>
	<p class="message">
		{#if screen.error === InstallError.NO_USERNAME}
			Please provide a valid username.
		{:else if screen.error === InstallError.INVALID_USERNAME}
			The username you provided has invalid characters.
		{:else if screen.error === InstallError.PASSWORD_MISMATCH}
			Your passwords do not match. Please try again.
		{:else if screen.error === InstallError.NO_EMAIL}
			You must provide an email address.
		{:else}
			Sorry, that is not a valid email address. Email addresses look like <code
				>username@example.com</code
			>.
		{/if}
	</p>
{/if}

{#if screen.kind === 'welcome' || screen.kind === 'error'}
	{@const form = screen.form}
	<form id="setup" method="post" action="install.php?step=2" novalidate>
		<table class="form-table" role="presentation">
			<tbody>
				<tr>
					<th scope="row"><label for="weblog_title">Site Title</label></th>
					<td
						><input
							name="weblog_title"
							type="text"
							id="weblog_title"
							size="25"
							value={form.siteTitle}
						/></td
					>
				</tr>
				<tr>
					<th scope="row"><label for="user_login">Username</label></th>
					<td>
						<input
							name="user_name"
							type="text"
							id="user_login"
							size="25"
							aria-describedby="user-name-desc"
							value={form.username}
						/>
						<p id="user-name-desc">
							Usernames can have only alphanumeric characters, spaces, underscores, hyphens,
							periods, and the @ symbol.
						</p>
					</td>
				</tr>
				<tr class="form-field form-required user-pass1-wrap">
					<th scope="row">
						<label for="pass1"> Password </label>
					</th>
					<td>
						<div class="wp-pwd">
							<div class="password-input-wrapper">
								<input
									type="password"
									name="admin_password"
									id="pass1"
									class="regular-text"
									autocomplete="new-password"
									spellcheck="false"
									data-reveal="1"
									data-pw={form.initialPassword}
									aria-describedby="pass-strength-result admin-password-desc"
								/>
								<div id="pass-strength-result" aria-live="polite"></div>
							</div>
							<button
								type="button"
								class="button wp-hide-pw hide-if-no-js"
								data-start-masked={form.passwordSubmitted ? '1' : '0'}
								data-toggle="0"
								aria-label="Hide password"
							>
								<span class="dashicons dashicons-hidden"></span>
								<span class="text">Hide</span>
							</button>
						</div>
						<p id="admin-password-desc">
							<span class="description important hide-if-no-js">
								<strong>Important:</strong>
								You will need this password to log&nbsp;in. Please store it in a secure location.</span
							>
						</p>
					</td>
				</tr>
				<tr class="form-field form-required user-pass2-wrap hide-if-js">
					<th scope="row">
						<label for="pass2"
							>Repeat Password
							<span class="description">(required)</span>
						</label>
					</th>
					<td>
						<input
							type="password"
							name="admin_password2"
							id="pass2"
							autocomplete="new-password"
							spellcheck="false"
						/>
					</td>
				</tr>
				<tr class="pw-weak">
					<th scope="row">Confirm Password</th>
					<td>
						<label>
							<input type="checkbox" name="pw_weak" class="pw-checkbox" />
							Confirm use of weak password
						</label>
					</td>
				</tr>
				<tr>
					<th scope="row"><label for="admin_email">Your Email</label></th>
					<td
						><input
							name="admin_email"
							type="email"
							id="admin_email"
							size="25"
							aria-describedby="admin-email-desc"
							value={form.email}
						/>
						<p id="admin-email-desc">Double-check your email address before continuing.</p></td
					>
				</tr>
				<tr>
					<th scope="row">Search engine visibility</th>
					<td>
						<fieldset>
							<legend class="screen-reader-text"><span> Search engine visibility </span></legend>
							<label for="blog_public"
								><input
									name="blog_public"
									type="checkbox"
									id="blog_public"
									aria-describedby="privacy-desc"
									value={DISCOURAGE_SEARCH_ENGINES}
									checked={form.discourageSearchEngines}
								/>
								Discourage search engines from indexing this site</label
							>
							<p id="privacy-desc" class="description">
								It is up to search engines to honor this request.
							</p>
						</fieldset>
					</td>
				</tr>
			</tbody>
		</table>
		<p class="step">
			<input
				type="submit"
				name="Submit"
				id="submit"
				class="button button-large"
				value="Install WordPress"
			/>
		</p>
		<input type="hidden" name="language" value={form.language} />
	</form>
{:else if screen.kind === 'success'}
	<h1>Success!</h1>

	<p>WordPress has been installed. Thank you, and enjoy!</p>

	<table class="form-table install-success">
		<tbody>
			<tr>
				<th>Username</th>
				<td>{screen.username}</td>
			</tr>
			<tr>
				<th>Password</th>
				<td>
					{#if screen.generatedPassword === null}
						<p><em>Your chosen password.</em></p>
					{:else}
						<code>{screen.generatedPassword}</code><br />
						<p>
							<strong><em>Note that password</em></strong> carefully! It is a <em>random</em> password
							that was generated just for you.
						</p>
					{/if}
				</td>
			</tr>
		</tbody>
	</table>

	<p class="step"><a href={resolve('/wp-login.php')}>Log In</a></p>
{/if}
