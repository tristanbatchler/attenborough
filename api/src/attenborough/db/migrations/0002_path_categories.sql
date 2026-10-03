-- Path categories: what a request was after (docs/plan-patterns.md).

-- What a request's path was after, as path_category() (below) guesses it.
CREATE TYPE path_category AS ENUM (
    'homepage', 'crawlers', 'secrets', 'backups', 'debug', 'exploits', 'wordpress', 'webshells',
    'logins', 'apis', 'other'
);

-- What a request's path was after: an inference from the path alone, as sent (a percent-encoded
-- probe such as /%2eenv is 'other'). The first rule that matches wins. Never stored, so changing a
-- rule (CREATE OR REPLACE in a new migration) recategorises every past request too.
CREATE FUNCTION path_category(path TEXT) RETURNS path_category
LANGUAGE sql IMMUTABLE PARALLEL SAFE
RETURN (CASE
    WHEN path = '/' THEN 'homepage'
    WHEN path ~* '^/(\.well-known/)?(robots\.txt|sitemap[^/]*\.xml|favicon[^/]*|apple-touch-icon[^/]*|(app-)?ads\.txt|sellers\.json|llms\.txt|humans\.txt|security\.txt)$'
        THEN 'crawlers'
    -- Credentials and configuration: dotfiles, environment files, deployment and app config.
    WHEN path ~* '(^|/)\.(env|git|svn|hg|aws|ssh|docker|npmrc|bash_history|bashrc|ftpconfig|remote-sync\.json|vscode|idea|ds_store)|\.env$|^/env(\.|$)|/@vite/env|(^|/)(wp-config\.php|config\.(json|js|ini|xml|env|ya?ml|php|inc\.php)|appsettings[^/]*\.json|secrets?\.(json|ya?ml)|user_secrets\.yml|credentials|database\.php|app\.php|aws\.(json|ya?ml)|docker-compose[^/]*\.ya?ml|dockerfile|\.gitlab-ci\.yml|package\.json|deploy\.sh|web\.xml|server\.key|id_(rsa|ed25519)|sftp(-config)?\.json|ftp-sync\.json|service\.pwd|env\.js|deployment-config\.json)'
        THEN 'secrets'
    WHEN path ~* '\.(sql|zip|tar|gz|tgz|rar|7z|bak|old|backup|save|swp|log)$' THEN 'backups'
    -- Debugging and diagnostics pages that leak a server's internals.
    WHEN path ~* 'php[-_]?info|(^|/)(info|i|pi)\.php|actuator|_profiler|telescope|trace\.axd|server-status|_ignition|rails/info|debug|heapdump|configprops|/manage(ment)?/env|^/(health|status|version|metrics)$'
        THEN 'debug'
    -- Probes for specific, known vulnerabilities: a curated list, from what the honeypot has seen.
    WHEN path ~* 'eval-stdin\.php|gponform|boaform|cgi-bin/luci|sdk/weblanguage|metadatauploader|/ecp/|meta-inf/|containers/json|hnap1|onvif|^/wsman|hello\.world|test\.hello|gravitysmtp|ztp_gate|cmdb/system|fgt_lang|nc_gina_ver|rdx_en\.json|druid/|geoserver|^/hudson|autodiscover|_layouts/|owa/auth/x\.js'
        THEN 'exploits'
    WHEN path ~* '(^|/)(wp-[^/]*|xmlrpc\.php)' THEN 'wordpress'
    -- Any other PHP file: most are guesses at a web shell someone else left behind.
    WHEN path ~* '\.php[0-9]?$' THEN 'webshells'
    -- Sign-in pages of VPNs, appliances and admin consoles.
    WHEN path ~* 'log[io]n|sign[-_]?in|auth|admin|console|portal|vpn|\+csco[et]\+|global-protect|dana-na|^/remote|sonic|logonpoint|/owa/|rdweb|rashtml5|cpanel|whm|phpmyadmin|webui|webclient|dashboard\.jspa|^/iam/'
        THEN 'logins'
    WHEN path ~* '(^|/)(api|graphql|gql|v[0-9]+|mcp|sse|ws|rest)(/|$)|\.well-known/(mcp|agents?(-card)?\.json)|_catalog'
        THEN 'apis'
    ELSE 'other'
END)::path_category;
