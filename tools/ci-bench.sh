#!/usr/bin/env bash
# The bench CI runs on: the tools it needs, and Frappe itself built once when no cached bench was restored.
# Used by ci.yml (every job) and cache-bench.yml (which saves the result on main), so the two cannot drift.
# Usage: tools/ci-bench.sh tests|walk          The Frappe release is in .github/frappe-version, the one place it is written.
set -euo pipefail
kind="${1:?usage: tools/ci-bench.sh tests|walk}"
here="$(cd "$(dirname "$0")/.." && pwd)"
version="$(tr -d '[:space:]' < "$here/.github/frappe-version")"
bench_path="${LIFEOS_BENCH_PATH:-/home/runner/frappe-bench}"

sudo apt-get update -qq && sudo apt-get install -y -qq mariadb-client libmariadb-dev tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin tesseract-ocr-ben ocrmypdf ffmpeg >/dev/null  # issue 104: the tools that read files on the server
npm install -g yarn >/dev/null
pip install -q frappe-bench
[ "$kind" = walk ] && pipx install semgrep >/dev/null

if [ -d "$bench_path/apps/frappe" ]; then
  echo "bench: restored from the cache, not building"
  exit 0
fi
echo "bench: building Frappe $version ($kind)"
if [ "$kind" = walk ]; then
  # with its own assets built (the desk and login pages), and developer mode as on the Docker bench
  bench init --skip-redis-config-generation --python "$(which python)" --frappe-branch "$version" "$bench_path"
  (cd "$bench_path" && bench set-config -g developer_mode 1)
else
  bench init --skip-redis-config-generation --skip-assets --python "$(which python)" --frappe-branch "$version" "$bench_path"
fi
