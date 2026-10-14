#!/usr/bin/env bash
# Clean-room check: fresh clone, setup, tests and a full reproduce, then diff against the committed
# results. Every file must match except timings.json (wall-clock solve times).
set -euo pipefail

cd "$(dirname "$0")/.."
repo="$(pwd)"
room="$(mktemp -d)"
trap 'rm -rf "$room"' EXIT

git clone --quiet "$repo" "$room/lading"
cd "$room/lading"
uv sync --frozen --quiet
uv run pytest -q
uv run python -m evaluation.harness reproduce

status=0
for f in "$repo"/results/*.json; do
  name="$(basename "$f")"
  [[ "$name" == "timings.json" ]] && continue
  if cmp -s "$f" "results/$name"; then
    echo "identical  $name"
  else
    echo "DIFFERENT  $name"
    status=1
  fi
done
exit $status
