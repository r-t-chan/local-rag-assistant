#!/usr/bin/env bash
# Generates a random API key into .env if one doesn't already exist.
# docker-compose.yml reads API_KEY from .env automatically and refuses to
# start the app without it (fail closed, not open).
#
# Note: bootstrapping data/kiwix/library.xml is handled by the kiwix-init
# service in docker-compose.yml, not here — that way it's self-healing on
# every `docker compose up` (including for existing deployments that never
# re-run this script) rather than a one-time setup step that's easy to miss.
set -euo pipefail

ENV_FILE=".env"

if [ -f "$ENV_FILE" ] && grep -q '^API_KEY=' "$ENV_FILE"; then
  echo "$ENV_FILE already has an API_KEY set — leaving it as-is."
  exit 0
fi

KEY=$(python3 -c "import secrets; print(secrets.token_hex(24))")
echo "API_KEY=$KEY" >> "$ENV_FILE"
echo "Generated a new API key in $ENV_FILE."
echo "You'll be prompted for it once in the browser on first load (it's then cached in localStorage)."
echo "Key: $KEY"
