#!/bin/sh
# Downloads this month's DB-IP Lite databases (City Lite and ASN Lite, CC BY 4.0) into the directory
# the API's container reads them from (docker-compose.yml), then restarts the API to open them.
# Addresses already located keep the location they got, with the older databases' dates; only new
# visitors get the new ones (api/src/attenborough/geolocation.py).
#
# As root, from the repository's root: `sh deploy/update-geoip.sh`. DB-IP publishes new databases
# at the start of each month; run it monthly from root's crontab (deploy/README.md). Both files are
# downloaded completely before either replaces the old one, so a failed download changes nothing.
# The restart takes a few seconds, during which the decoy's reports fail and those visits are lost.
set -eu

directory=/var/lib/attenborough/geoip
month=$(date -u +%Y-%m)
download=$(mktemp -d)
trap 'rm -rf "$download"' EXIT

for database in city asn; do
    curl -fsS --retry 3 -o "$download/$database.mmdb.gz" \
        "https://download.db-ip.com/free/dbip-$database-lite-$month.mmdb.gz"
    gunzip "$download/$database.mmdb.gz"
done

install -d -m 0755 "$directory"
for database in city asn; do
    install -m 0644 "$download/$database.mmdb" "$directory/dbip-$database-lite.mmdb"
done
echo "Installed DB-IP's $month databases in $directory"

# Not on the first run, before the API exists: it opens them when it starts.
if [ -n "$(docker compose ps -q api)" ]; then
    docker compose restart api
fi
