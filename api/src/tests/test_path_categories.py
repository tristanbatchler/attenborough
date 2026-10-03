"""The rules of path_category() (schema.sql), on paths the live honeypot received. Needs the
development database (api/.env), and only reads."""

import pytest
from psycopg import AsyncConnection

from attenborough.db import queries
from attenborough.db.enums import PathCategory

EXAMPLES = {
    PathCategory.HOMEPAGE: ["/"],
    PathCategory.CRAWLERS: [
        "/robots.txt",
        "/favicon.ico",
        "/.well-known/security.txt",
        "/app-ads.txt",
        "/sitemap.xml",
    ],
    PathCategory.SECRETS: [
        "/.env",
        "/.env.production",
        "/api/.env",
        "/sendgrid.env",
        "/env",
        "/@vite/env",
        "/.git/config",
        "/media../.git/config",
        "/.aws/credentials",
        "/.ssh/id_rsa",
        "/.vscode/sftp.json",
        "/wp-config.php.bak",
        "/config.json",
        "/docker-compose.prod.yml",
        "/appsettings.json",
    ],
    PathCategory.BACKUPS: [
        "/backup.zip",
        "/dump.sql",
        "/backup.tar.gz",
        "/storage/logs/laravel.log",
    ],
    PathCategory.DEBUG: [
        "/phpinfo.php",
        "/info.php",
        "/actuator/env",
        "/_profiler/phpinfo",
        "/telescope/requests",
        "/server-status",
        "/version",
    ],
    PathCategory.EXPLOITS: [
        "/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
        "/GponForm/diag_Form",
        "/cgi-bin/luci/",
        "/SDK/webLanguage",
        "/developmentserver/metadatauploader",
        "/containers/json",
        "/geoserver/web/",
        "/autodiscover/autodiscover.json",
        "/owa/auth/x.js",
    ],
    PathCategory.WORDPRESS: [
        "/wp-login.php",
        "/xmlrpc.php",
        "/wp-admin/install.php",
        "/wp-content/plugins/hellopress/wp_filemanager.php",
    ],
    PathCategory.WEBSHELLS: ["/1.php", "/xiugai.php", "//adminfuns.php", "/index.php"],
    PathCategory.LOGINS: [
        "/+CSCOE+/logon.html",
        "/global-protect/login.esp",
        "/remote/login",
        "/dana-na/auth/url_default/welcome.cgi",
        "/owa/auth/logon.aspx",
        "/admin",
        "/console/",
        "/___proxy_subdomain_cpanel",
    ],
    PathCategory.APIS: [
        "/graphql",
        "/api/gql",
        "/mcp",
        "/.well-known/agent-card.json",
        "/v2/_catalog",
    ],
    PathCategory.OTHER: ["/about", "/lander/", "/%2eenv", "/aab9"],
}


def test_every_category_has_examples():
    assert set(EXAMPLES) == set(PathCategory)


@pytest.mark.anyio
async def test_each_path_gets_its_category(db_conn: AsyncConnection):
    # One test for every path, rather than one per path, so a broken rule shows all it breaks.
    got = {
        path: await queries.categorise_path(db_conn, path=path)
        for paths in EXAMPLES.values()
        for path in paths
    }
    expected = {
        path: category for category, paths in EXAMPLES.items() for path in paths
    }
    assert got == expected
