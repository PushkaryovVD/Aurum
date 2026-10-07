#!/bin/sh
# Runs automatically before nginx starts (official nginx image convention:
# every executable script in /docker-entrypoint.d/ is sourced on boot).
#
# Aurum has an invite-only application identity/session layer. HTTP Basic Auth
# is a separate optional perimeter in front of the whole installation; it does
# not replace Aurum users, sessions or workspace authorization. This script
# enables that outer nginx gate for the UI and API, except the health endpoint
# required by Docker and external uptime monitors.
set -eu

AUTH_FRAGMENT=/etc/nginx/basic-auth.conf
AUTH_STATUS=/usr/share/nginx/html/auth-status.json

if [ -n "${AURUM_BASIC_AUTH_USER:-}" ] && [ -n "${AURUM_BASIC_AUTH_PASSWORD:-}" ]; then
  HASH="$(openssl passwd -apr1 "$AURUM_BASIC_AUTH_PASSWORD")"
  echo "${AURUM_BASIC_AUTH_USER}:${HASH}" > /etc/nginx/.htpasswd
  cat > "$AUTH_FRAGMENT" <<EOF
auth_basic "Aurum";
auth_basic_user_file /etc/nginx/.htpasswd;
EOF
  printf '{"enabled":true}\n' > "$AUTH_STATUS"
  echo "[aurum] Basic auth enabled for user '${AURUM_BASIC_AUTH_USER}'."
else
  : > "$AUTH_FRAGMENT"
  printf '{"enabled":false}\n' > "$AUTH_STATUS"
  echo "[aurum] Basic Auth perimeter is disabled." >&2
  echo "[aurum] Aurum application authentication remains independent. Required-auth mode" >&2
  echo "[aurum] keeps finance closed; explicit legacy auth-disabled mode exposes finance" >&2
  echo "[aurum] to every network client unless another perimeter protects the instance." >&2
fi
