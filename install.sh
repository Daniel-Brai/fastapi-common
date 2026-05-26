#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="Daniel-Brai"
REPO_NAME="fastapi-common"
BRANCH="main"

usage() {
  cat <<EOF
Usage: $0 <folder> [destination]

Downloads the GitHub repository archive for ${REPO_OWNER}/${REPO_NAME} and copies the specified folder
from the repository root into your local destination.

Arguments:
  folder        The folder path inside the repository to copy, e.g. "mailer" or "auth".
  destination   Optional local destination directory (defaults to current directory).

Example:
  $0 mailer
  $0 auth ./local-auth
EOF
}

if [[ ${#@} -lt 1 || ${#@} -gt 2 ]]; then
  usage
  exit 1
fi

FOLDER="$1"
DESTINATION="${2:-.}"

TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

ARCHIVE_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/${BRANCH}.tar.gz"
ARCHIVE_PATH="$TMPDIR/repo.tar.gz"

printf 'Downloading %s from GitHub...\n' "$ARCHIVE_URL"
curl -fsSL "$ARCHIVE_URL" -o "$ARCHIVE_PATH"

printf 'Extracting archive...\n'
tar -xzf "$ARCHIVE_PATH" -C "$TMPDIR"

EXTRACTED_ROOT="$(find "$TMPDIR" -maxdepth 1 -type d -name "${REPO_NAME}-*" | head -n 1)"
if [[ -z "$EXTRACTED_ROOT" ]]; then
  echo "Error: failed to extract repository archive." >&2
  exit 1
fi

SRC_PATH="$EXTRACTED_ROOT/$FOLDER"
if [[ ! -e "$SRC_PATH" ]]; then
  echo "Error: folder '$FOLDER' does not exist in the repository root." >&2
  exit 1
fi

mkdir -p "$DESTINATION"

if [[ -d "$SRC_PATH" ]]; then
  cp -R "$SRC_PATH" "$DESTINATION"
else
  cp "$SRC_PATH" "$DESTINATION"
fi

printf 'Copied %s to %s\n' "$FOLDER" "$DESTINATION"
