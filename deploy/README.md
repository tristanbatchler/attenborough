# Deploying Attenborough

Attenborough runs on one host that also runs other services. Docker Compose runs the three apps, while nginx and PostgreSQL run on the host itself. This is how to set it up, update it, check it and recover it. The design and the reasons behind it are in `../docs/plan-first-field-season.md`.

```
internet ─▶ nginx (host) ─┬─ any name, the bare IP, the decoy's domain ─▶ /run/attenborough/decoy/decoy.sock ─▶ decoy ─┐
                          │                                                                                          ├─▶ api ─▶ /var/run/postgresql ─▶ PostgreSQL (host)
Cloudflare ─▶ nginx ──────┴─ the exhibit's domain (Cloudflare's addresses only) ─▶ /run/attenborough/web/web.sock ─▶ web ┘
```

## How it is contained

The decoy invites hostile traffic, on a machine shared with other services. Everything that runs it is built so that a compromised container can reach nothing it doesn't need:

- **No published ports.** nginx reaches the decoy and web through unix sockets in `/run/attenborough/`, in directories only nginx's group (`www-data`) can enter (`tmpfiles.conf`). Nothing listens on any interface, so nothing on the LAN or the host can connect to the apps around nginx.
- **No route out.** The decoy and web each share one network with the API, and nothing else. Both networks are `internal` with gateway mode `isolated`: the bridge has no address on the host, so a container can reach neither the internet, the LAN, the host's own services (PostgreSQL, SSH, other containers' published ports) nor the other containers. The decoy can't reach web. A plain `internal` network isn't enough: its containers can still reach every host service listening on all interfaces, and a host firewall may well admit Docker's address ranges.
- **The API's only ways out** are PostgreSQL's unix socket, mounted read-only, and nginx's socket to Google's token endpoint, for the admin login (`/run/attenborough/google`, read-only; nginx forwards that one path to Google and nothing else). It connects as the app role, which can read and write rows but never change the schema or delete rows (`database.sql`). Like any role, it can connect to the server's other databases that leave PostgreSQL's default `CONNECT` for everyone in place, but it has no privileges on their tables.
- **Every container** runs as uid 10001 (which owns nothing on the host), with a read-only root filesystem, no capabilities, `no-new-privileges`, Docker's default seccomp and AppArmor profiles, and limits on memory, CPU and processes. Logs are rotated (5 × 10 MB per container).
- **Only the decoy's address may name a visitor** to the API (`FORWARDED_ALLOW_IPS`, the decoy's fixed address on its own network). nginx overwrites `X-Forwarded-For` with the visitor's address, so no visitor can choose their own.
- **The exhibit answers only Cloudflare.** Anyone else asking this host for the exhibit's domain gets no response at all, so the exhibit can't be traced to this host by asking for it here.

What remains is a flaw in the kernel or Docker itself that lets a process out of its container. Docker's user-namespace remapping (`userns-remap`) would narrow that further, but it is a daemon-wide setting that changes every other container on this host, so it isn't used. `check-isolation.sh` proves the rest after every deployment.

## Setting up the host (once)

Run from the repository's root on the host, e.g. `~/attenborough`, cloned from GitHub (`git clone https://github.com/tristanbatchler/attenborough.git`). The repository is public: everything that identifies the honeypot lives only in `.env` and in the rendered nginx site, which are never committed.

1. **DNS.** The decoy's domain, a domain of its own unrelated to the exhibit's: `A` records for the domain itself and `www`, both straight to the host's public IP (no `CNAME` to another of your names, and no registrar redirect: either would name or bypass the host), **DNS only** (never proxied: Cloudflare would block or challenge the scanners the honeypot exists to see, and replace their addresses with its own). The exhibit's domain: **proxied** through Cloudflare, with SSL/TLS mode **Full (strict)**. Ports 80 and 443 forwarded to the host.

2. **Settings.** `cp .env.example .env && chmod 600 .env`, then fill it in. `HONEYPOT_ADDRESSES` must list the decoy's domain and the host's public IP: the exhibit hides each of them (`../api/README.md`, "Hiding where the honeypot is"). If the public IP ever changes, add the new one and keep the old. The admin login needs a Google OAuth client (Google Cloud Console, APIs & Services → Credentials, a "Web application") whose authorised redirect URI is `https://<exhibit domain>/auth/google/callback`: its ID and secret go in `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, and the Google accounts allowed in, comma-separated, in `ADMIN_EMAILS`.

3. **The database and its roles.** As a PostgreSQL superuser, which asks for the two passwords you put in `.env`:

   ```sh
   psql -U postgres -h /var/run/postgresql -f deploy/database.sql
   ```

   It creates the database (owned by the owner role), the app role, and the privileges between them. It never drops anything: if the database or a role already exists, it stops.

4. **The socket directories,** now and at every boot:

   ```sh
   sudo cp deploy/tmpfiles.conf /etc/tmpfiles.d/attenborough.conf
   sudo systemd-tmpfiles --create /etc/tmpfiles.d/attenborough.conf
   ```

5. **nginx.** A certificate that names nothing, for connections to the bare IP; the decoy's shared proxy settings, with the directory Let's Encrypt's challenges are served from; and the site, rendered from `.env`. The decoy domain's certificate can only be issued once nginx answers for it, so the first render borrows the exhibit's certificate for it, then certbot issues the real one and the site is rendered again:

   ```sh
   sudo mkdir -p /etc/nginx/attenborough /var/www/attenborough-acme
   sudo openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj '/CN=localhost' \
       -keyout /etc/nginx/attenborough/nameless.key -out /etc/nginx/attenborough/nameless.crt
   sudo cp deploy/nginx/decoy-proxy.conf /etc/nginx/attenborough/
   render() { (set -a && . ./.env && set +a
       [ "${1:-}" = first ] && DECOY_TLS_CERTIFICATE_DIR=$EXHIBIT_TLS_CERTIFICATE_DIR
       envsubst '${DECOY_DOMAIN} ${EXHIBIT_DOMAIN} ${DECOY_TLS_CERTIFICATE_DIR} ${EXHIBIT_TLS_CERTIFICATE_DIR}' \
           < deploy/nginx/attenborough.conf | sudo tee /etc/nginx/sites-available/attenborough > /dev/null) }
   render first   # borrows the exhibit's certificate for the decoy, until it has its own
   sudo ln -s /etc/nginx/sites-available/attenborough /etc/nginx/sites-enabled/attenborough
   sudo nginx -t && sudo systemctl reload nginx
   . ./.env && sudo certbot certonly --webroot -w /var/www/attenborough-acme \
       -d "$DECOY_DOMAIN" -d "www.$DECOY_DOMAIN" --deploy-hook 'systemctl reload nginx'
   render
   sudo nginx -t && sudo systemctl reload nginx
   ```

   certbot's timer renews the decoy's certificate through the same directory, and reloads nginx. Each issuance is published in the Certificate Transparency logs, which scanners watch for new names: that is the decoy's main advertisement, and why it has a certificate of its own rather than a wildcard shared with other names.

   The site makes the decoy nginx's `default_server` on ports 80 and 443: every request that matches no other site on this host now reaches the decoy, instead of the first site in `sites-enabled`. No other site may also claim `default_server`.

6. **The geolocation databases.** DB-IP's free City Lite and ASN Lite (CC BY 4.0), which the API reads from `/var/lib/attenborough/geoip`, mounted read-only (`../api/README.md`, "Geolocation"). The API refuses to start without them. Download them now, and every month from root's crontab, on the 3rd (DB-IP publishes at the start of the month); the script restarts the API to open the new ones:

   ```sh
   sudo sh deploy/update-geoip.sh
   echo "0 6 3 * * root cd $PWD && sh deploy/update-geoip.sh" | sudo tee /etc/cron.d/attenborough-geoip
   ```

7. **Build, migrate, start:**

   ```sh
   docker compose build
   docker compose run --rm migrate   # a new database gets every migration
   docker compose up -d
   ```

8. Run every check below.

## Updating

```sh
git pull
docker compose build
docker compose run --rm migrate      # applies any new migrations, as the owner role; harmless if there are none
docker compose up -d
```

Then run the checks. If `deploy/nginx/` changed, copy `decoy-proxy.conf` again and render and reload the site (step 5's `render` and the reload).

**The admin area** (the release that added it): fill in the admin settings in `.env` (step 2), copy `tmpfiles.conf` again and create its directories (step 4), copy and render the nginx site again (step 5: it now also listens on the socket to Google), then build, migrate and start as above. The migration lets the app role delete login states and sessions; nothing else changes about its privileges.

**Turning geolocation on** (the release that added it): before `docker compose up -d`, set up the databases as in step 6, and after it, locate the addresses seen so far: `docker compose exec api python scripts/locate_ips.py`.

## Changing the decoy's domain

1. DNS for the new domain as in step 1. Leave the old name's record in place until the new one works.
2. In `.env`: the new `DECOY_DOMAIN`, `DECOY_TLS_CERTIFICATE_DIR=/etc/letsencrypt/live/<new domain>`, and the new domain **added** to `HONEYPOT_ADDRESSES` (keep the old one: older records contain it).
3. Issue the certificate and render the site: step 5's `certbot` command, then `render` and the reload. The old site still answers for the new name meanwhile, as the `default_server`, so the challenge succeeds.
4. `docker compose up -d`: recreates the API with the new `HONEYPOT_ADDRESSES`.
5. Check the new domain from outside your network, then remove the old name's DNS record.

**If the API won't start,** read why: `docker compose logs api`. Without a terminal it never changes the schema itself, so a database that needs migrations makes it refuse with `refusing to start` and the command to run. A database whose applied migrations differ from `migrations/` (`diverged`) means a migration was edited after it was applied: never reset production; write a new migration that gets from what was applied to what is wanted.

**Before a migration,** keep a copy of the data: `pg_dump -U postgres -h /var/run/postgresql -Fc attenborough > attenborough-$(date +%F).dump` (restore: `pg_restore -U postgres -h /var/run/postgresql -d attenborough --clean attenborough-<date>.dump`). Each migration runs in a transaction, so a failing one changes nothing, but one that succeeds and is wrong can only be undone from a copy. There are no automatic backups.

## Checks after every deployment

On the host:

```sh
docker compose ps                         # api, decoy and web up; nothing published (no `->` under PORTS; the API's bare 8000/tcp is only its image's declared port)
sh deploy/check-isolation.sh              # must end "isolation: all checks passed"
docker compose logs --since 1h | grep -vE ' INFO|INFO:'   # anything that isn't an INFO line
docker compose exec api python scripts/exhibit_latency.py --base-url http://127.0.0.1:8000
```

From a machine **outside** the host's network (a phone's hotspot will do), with the domains and IP from `.env`:

```sh
# Nothing but nginx answers: every other port is closed or filtered.
nc -zv -w 3 <public IP> 8000; nc -zv -w 3 <public IP> 5432

# The decoy answers on its domain and on the bare IP, over HTTP and HTTPS, and looks like PHP on nginx.
curl -s  http://<decoy domain>/wp-login.php | grep -E '<script|_app|svelte|<!--'   # prints nothing
curl -sk https://<public IP>/wp-login.php    | grep -E '<script|_app|svelte|<!--'   # prints nothing
curl -sI http://<public IP>/ | grep -i '^server'                                     # "Server: nginx", no version

# A forged X-Forwarded-For is never recorded as the visitor's address.
curl -s -o /dev/null -H 'X-Forwarded-For: 203.0.113.99' -H 'X-Real-IP: 203.0.113.98' https://<decoy domain>/wp-login.php
curl -s https://<exhibit domain>/ip/203.0.113.99 | grep -c 'No activity has been recorded'   # 1
curl -s https://<exhibit domain>/ip/203.0.113.98 | grep -c 'No activity has been recorded'   # 1
curl -s https://<exhibit domain>/ip/<your outside IP> | grep -c 'wp-login.php'              # at least 1

# The exhibit hides the honeypot: the request above, opened from the exhibit, shows Host: [honeypot].
curl -s https://<exhibit domain>/ | grep -ciE '<decoy domain>|<public IP>'   # 0

# The exhibit is only reachable through Cloudflare: asked directly, the host doesn't answer.
curl -sk --resolve <exhibit domain>:443:<public IP> https://<exhibit domain>/ -o /dev/null -w '%{http_code}\n'   # 000
```

## What this setup doesn't do

- **No automatic backups.** Take a `pg_dump` before migrations (above); the honeypot's data is otherwise only in the one database.
- **No retention.** Every hit, body and login attempt is kept. A hit stores at most 64 KiB of its body. Watch the database's size (`SELECT pg_size_pretty(pg_database_size('attenborough'))`) and the host's disk, especially in the first weeks.
- **Cloudflare's ranges change rarely, but they do.** They are listed in `nginx/attenborough.conf` (from https://www.cloudflare.com/ips/, with the date fetched). If Cloudflare adds one, readers routed through it get no answer until the list is updated.
