#!/usr/bin/env bash
# Generates a random API key into .env if one doesn't already exist, and
# bootstraps an empty Kiwix library file — kiwix-serve crash-loops if that
# file doesn't exist at all (verified directly), so it has to exist before
# the first `docker compose up`, even with zero ZIM files downloaded yet.
set -euo pipefail

ENV_FILE=".env"
LIBRARY_FILE="data/kiwix/library.xml"

if [ -f "$ENV_FILE" ] && grep -q '^API_KEY=' "$ENV_FILE"; then
  echo "$ENV_FILE already has an API_KEY set — leaving it as-is."
else
  KEY=$(python3 -c "import secrets; print(secrets.token_hex(24))")
  echo "API_KEY=$KEY" >> "$ENV_FILE"
  echo "Generated a new API key in $ENV_FILE."
  echo "You'll be prompted for it once in the browser on first load (it's then cached in localStorage)."
  echo "Key: $KEY"
fi

if [ -f "$LIBRARY_FILE" ]; then
  echo "$LIBRARY_FILE already exists — leaving it as-is."
else
  mkdir -p "$(dirname "$LIBRARY_FILE")"
  cat > "$LIBRARY_FILE" <<'EOF'
<?xml version="1.0" encoding="UTF-8" ?>
<library version="20110515">
</library>
EOF
  echo "Created an empty $LIBRARY_FILE (kiwix-serve runs fine with zero books;"
  echo "run ./scripts/download_wikipedia_zim.sh to add Wikipedia)."
fi
