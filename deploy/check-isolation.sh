#!/bin/sh
# Proves the containers' isolation (docker-compose.yml) from inside each running container: the
# decoy and web reach the API and nothing else, and the API reaches nothing at all over the network
# (PostgreSQL only through its socket). Run on the host from the repository's root after every
# deployment: `sh deploy/check-isolation.sh`. Prints one line per attempt and exits 1 if anything
# that must be unreachable answered, or the API didn't.
set -u

# The host's own LAN address and its router, found from the host's default route.
gateway=$(ip route show default | awk '{ print $3; exit }')
host_ip=$(ip route get "$gateway" | awk '{ for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit } }')

# Attempts a TCP connection from inside a container; prints "open" or why not.
probe_node='const [h, p] = process.argv.slice(1); const s = require("net").connect({ host: h, port: +p }); s.setTimeout(3000); s.on("connect", () => { console.log("open"); process.exit(0); }); s.on("timeout", () => { console.log("timeout"); process.exit(0); }); s.on("error", (e) => { console.log(e.code); process.exit(0); });'
probe_python='import socket, sys
try:
    socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=3).close(); print("open")
except OSError as e:
    print(type(e).__name__)'

failures=0

attempt() { # service, host, port, expected (open | closed)
    case $1 in
        api) result=$(docker compose exec -T api python -c "$probe_python" "$2" "$3" 2>&1) ;;
        *) result=$(docker compose exec -T "$1" node -e "$probe_node" "$2" "$3" 2>&1) ;;
    esac
    if { [ "$4" = open ] && [ "$result" = open ]; } || { [ "$4" = closed ] && [ "$result" != open ]; }; then
        verdict=ok
    else
        verdict=FAIL
        failures=$((failures + 1))
    fi
    printf '%-5s %-6s -> %-22s %-8s (expected %s)\n' "$verdict" "$1" "$2:$3" "$result" "$4"
}

for service in decoy web; do
    attempt "$service" api 8000 open
done
for service in decoy web api; do
    attempt "$service" 1.1.1.1 443 closed           # the internet
    attempt "$service" "$gateway" 80 closed         # the LAN's router
    attempt "$service" "$host_ip" 22 closed         # the host's own services, by its LAN address
    attempt "$service" "$host_ip" 5432 closed       #   PostgreSQL over TCP
    attempt "$service" "$host_ip" 443 closed        #   nginx
    attempt "$service" 172.17.0.1 8000 closed       # other containers' published ports, via Docker's default bridge
done
# Each app network's first address (the subnets in docker-compose.yml). A plain `internal` network
# gives it to the host's bridge, through which a container reaches every host service listening on
# all interfaces. With gateway mode `isolated` the bridge has no address, and Docker gives this one
# to a container (the API, which listens on neither port).
for target in "decoy 10.89.1.1" "web 10.89.2.1" "api 10.89.1.1" "api 10.89.2.1"; do
    set -- $target
    attempt "$1" "$2" 22 closed
    attempt "$1" "$2" 5432 closed
done

[ "$failures" -eq 0 ] && echo "isolation: all checks passed" || echo "isolation: $failures check(s) FAILED"
[ "$failures" -eq 0 ]
