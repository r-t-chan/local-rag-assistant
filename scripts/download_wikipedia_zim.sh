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
LIBRARY_DIR="${LIBRARY_DIR:-./data/kiwix}"
ZIM_URL="https://download.kiwix.org/zim/wikipedia/${ZIM_FILENAME}"
KIWIX_IMAGE="ghcr.io/kiwix/kiwix-serve:latest"

mkdir -p "$ZIM_DIR" "$LIBRARY_DIR"
# Resolve to absolute paths regardless of whether the overrides above are
# already absolute or relative — "$(pwd)/$ZIM_DIR" would silently double up
# and point at a bogus location if ZIM_DIR were already absolute.
ZIM_DIR="$(cd "$ZIM_DIR" && pwd)"
LIBRARY_DIR="$(cd "$LIBRARY_DIR" && pwd)"
LIBRARY_FILE="$LIBRARY_DIR/library.xml"

if [ ! -f "$LIBRARY_FILE" ]; then
  echo "Bootstrapping an empty $LIBRARY_FILE..."
  printf '<?xml version="1.0" encoding="UTF-8" ?>\n<library version="20110515">\n</library>\n' > "$LIBRARY_FILE"
fi

ZIM_PATH="$ZIM_DIR/$ZIM_FILENAME"
TMP_PATH="$ZIM_PATH.part"

echo "Downloading $ZIM_FILENAME (~12GB, full English Wikipedia article text, no images)..."
echo "This will take a while depending on your connection. Safe to re-run if interrupted (resumes)."
curl -L --fail -C - -o "$TMP_PATH" "$ZIM_URL"

echo "Verifying checksum..."
EXPECTED_SHA=$(curl -sL --fail "$ZIM_URL.sha256" | awk '{print $1}')
ACTUAL_SHA=$(sha256sum "$TMP_PATH" | awk '{print $1}')
if [ "$EXPECTED_SHA" != "$ACTUAL_SHA" ]; then
  echo "Checksum mismatch! Expected $EXPECTED_SHA, got $ACTUAL_SHA. Deleting partial download." >&2
  rm -f "$TMP_PATH"
  exit 1
fi
mv "$TMP_PATH" "$ZIM_PATH"
echo "Checksum verified."

echo "Registering $ZIM_FILENAME in $LIBRARY_FILE..."
# The registration writes to a .tmp copy and renames it over the real file
# on success, rather than editing library.xml in place. kiwix-serve's
# --monitorLibrary watches this same file for changes while running (with
# only read access — see docker-compose.yml); an in-place edit could be
# observed mid-write, whereas a rename is atomic, so it only ever sees the
# old complete file or the new complete file, never a partial one.
#
# --user matches the host user so kiwix-manage can write here: the running
# kiwix-serve container's default user (uid 1001) only ever needs read
# access to the library directory, but this one-off write needs to be the
# file's owner.
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$ZIM_DIR:/data/zim:ro" \
  -v "$LIBRARY_DIR:/config" \
  --entrypoint sh \
  "$KIWIX_IMAGE" \
  -c "cp /config/library.xml /config/library.xml.tmp && kiwix-manage /config/library.xml.tmp add /data/zim/$ZIM_FILENAME && mv /config/library.xml.tmp /config/library.xml"

echo "Done. If the kiwix service is already running, --monitorLibrary picks up"
echo "the change automatically — no restart needed."
