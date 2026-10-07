#!/bin/sh
# Give nginx a cryptographic identity toward the backend. CasaOS may rewrite
# Compose bridge subnets and static container addresses, so an IP-only trust
# boundary can reject the legitimate proxy after an otherwise healthy update.
set -eu

SECRET_FILE="${AURUM_AUTH_PROXY_SHARED_SECRET_FILE:-/run/aurum-secrets/proxy_shared_secret}"
FRAGMENT=/etc/nginx/proxy-identity.conf

if [ ! -s "$SECRET_FILE" ]; then
  echo "[aurum] Proxy identity secret is unavailable." >&2
  exit 1
fi

SECRET="$(cat "$SECRET_FILE")"
case "$SECRET" in
  *[!A-Za-z0-9+/=]*|'')
    echo "[aurum] Proxy identity secret has an invalid format." >&2
    exit 1
    ;;
esac

umask 077
cat > "$FRAGMENT" <<EOF
# Generated at container startup. Always overwrite a browser-supplied value.
proxy_set_header X-Aurum-Proxy-Token "$SECRET";
EOF