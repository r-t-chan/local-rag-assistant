#!/usr/bin/env bash
# Downloads a Wikipedia ZIM dump into data/zim/ and registers it in kiwix's
# library manifest (data/kiwix/library.xml) via kiwix-manage.
#
# ZIM filenames are dated snapshots (e.g. wikipedia_en_all_mini_2026-06.zim) —
# there is no stable "latest" alias that actually resolves, so the filename
# below is a known-good snapshot as of when this script was written. Check
# https://library.kiwix.org or https://download.kiwix.org/zim/wikipedia/ for
# the current filename if this one 404s, and override via ZIM_FILENAME.
set -euo pipefail

ZIM_FILENAME="${ZIM_FILENAME:-wikipedia_en_all_mini_2026-06.zim}"
ZIM_DIR="${ZIM_DIR:-./data/zim}"
LIBRARY_FILE="${LIBRARY_FILE:-./data/kiwix/library.xml}"
ZIM_URL="https://download.kiwix.org/zim/wikipedia/${ZIM_FILENAME}"
KIWIX_IMAGE="ghcr.io/kiwix/kiwix-serve:latest"

if [ ! -f "$LIBRARY_FILE" ]; then
  echo "$LIBRARY_FILE doesn't exist yet — run ./scripts/init_env.sh first." >&2
  exit 1
fi

mkdir -p "$ZIM_DIR"

echo "Downloading $ZIM_FILENAME (~12GB, full English Wikipedia article text, no images)..."
echo "This will take a while depending on your connection."
curl -L --fail -o "$ZIM_DIR/$ZIM_FILENAME" "$ZIM_URL"

echo "Registering $ZIM_FILENAME in $LIBRARY_FILE..."
# --user matches the host user so kiwix-manage can write the file: the
# running kiwix-serve container's default user (uid 1001) only ever needs
# read access to it, but this one-off write needs to be the file's owner.
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$(pwd)/$ZIM_DIR:/data/zim:ro" \
  -v "$(pwd)/$LIBRARY_FILE:/config/library.xml" \
  --entrypoint kiwix-manage \
  "$KIWIX_IMAGE" \
  /config/library.xml add "/data/zim/$ZIM_FILENAME"

echo "Done. If the kiwix service is already running, --monitorLibrary picks up"
echo "the change automatically — no restart needed."
