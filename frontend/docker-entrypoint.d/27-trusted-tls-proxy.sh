#!/bin/sh
# Runs before nginx starts, same convention as 25-allowed-hosts.sh next door.
#
# Decides what nginx tells the backend about plain-HTTP (port 80) requests:
# the scheme the visitor really used and the visitor's IP address.
#
# Default (AURUM_TRUSTED_TLS_PROXY unset or "none"): nothing a client sends is
# trusted. The scheme is nginx's own ($scheme = http) and the client is the TCP
# peer. This is the safe choice for direct LAN access.
#
# "cloudflare": Aurum is published through Cloudflare Tunnel, which ends HTTPS
# at Cloudflare and forwards plain HTTP to port 80. Without this the backend
# sees "http" while the browser's Origin says "https", so sign-in and every
# change are rejected as cross-origin. With it, a forwarded "https" is passed
# on and the visitor IP comes from CF-Connecting-IP, so rate limits are per
# visitor instead of one shared bucket for everybody behind the tunnel.
# Spoofing these headers from the LAN gains nothing over plain HTTP: browsers
# cannot add them to cross-site requests, so CSRF/origin protection holds.
set -eu

FRAGMENT=/etc/nginx/trusted-tls-proxy.conf
MODE="${AURUM_TRUSTED_TLS_PROXY:-none}"

case "$MODE" in
  cloudflare)
    cat > "$FRAGMENT" <<'EOF'
# Generated at container start by docker-entrypoint.d/27-trusted-tls-proxy.sh
# (AURUM_TRUSTED_TLS_PROXY=cloudflare).
map $http_x_forwarded_proto $aurum_port80_proto {
    https https;
    default $scheme;
}
map $http_cf_connecting_ip $aurum_port80_client {
    "" $remote_addr;
    default $http_cf_connecting_ip;
}
EOF
    echo "[aurum] Trusting Cloudflare Tunnel for visitor scheme and IP on port 80." >&2
    ;;
  none|"")
    cat > "$FRAGMENT" <<'EOF'
# Generated at container start by docker-entrypoint.d/27-trusted-tls-proxy.sh
# (AURUM_TRUSTED_TLS_PROXY=none): client-supplied headers are not trusted.
map $scheme $aurum_port80_proto {
    default $scheme;
}
map $remote_addr $aurum_port80_client {
    default $remote_addr;
}
EOF
    ;;
  *)
    echo "[aurum] AURUM_TRUSTED_TLS_PROXY must be 'none' or 'cloudflare', got '$MODE'." >&2
    exit 1
    ;;
esac
