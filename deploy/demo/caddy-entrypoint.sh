#!/bin/sh
set -eu

fail() { printf '%s\n' 'Demo proxy configuration refused.' >&2; exit 1; }
# Never use set -x or caddy --environ: the hash is process-local secret data.
DEMO_BASIC_AUTH_HASH=$(cat /run/secrets/demo_basic_auth_hash) || fail
printf '%s' "$DEMO_BASIC_AUTH_HASH" | grep -Eq '^\$2[aby]\$(0[4-9]|[12][0-9]|3[01])\$[./A-Za-z0-9]{53}$' || fail
printf '%s' "${DEMO_BASIC_AUTH_USER:-}" | grep -Eq '^[A-Za-z0-9_-]{1,64}$' || fail
printf '%s' "${DEMO_HOST:-}" | grep -Eq '^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$' || fail
case "${DEMO_TLS_DIRECTIVE:-}" in ''|'tls internal') ;; *) fail ;; esac
export DEMO_BASIC_AUTH_HASH
exec "$@"
