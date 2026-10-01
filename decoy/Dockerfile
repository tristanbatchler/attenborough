# The decoy: the fake sites the honeypot shows its visitors. Built and run by
# ../docker-compose.yml; see ../deploy/README.md.

FROM node:24-bookworm-slim AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Needs no settings: everything runtime-specific is read from $env/dynamic at startup.
RUN npm run build


FROM node:24-bookworm-slim

WORKDIR /app
# adapter-node bundles every devDependency into build/, so no node_modules are needed.
COPY --from=build /app/build ./build
COPY --from=build /app/package.json ./
ENV NODE_ENV=production

USER 10001:10001
# Listens on SOCKET_PATH, in a directory only it and nginx's group can enter (deploy/tmpfiles.conf).
# umask 0 makes the socket itself writable by nginx, which a socket needs to be connected to.
CMD ["sh", "-c", "umask 0 && exec node build"]
