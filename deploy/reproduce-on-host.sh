#!/usr/bin/env bash
# Run the evaluation on the deploy host (linux/amd64), in a fresh container, from a fresh clone of HEAD.
#
# HiGHS stops at a 0.5% optimality gap, and different CPUs can reach a different plan inside that gap.
# The console solves on the deploy host, so results/ is generated there: the live canonical run then
# matches results/canonical.json exactly.
#
#   deploy/reproduce-on-host.sh adopt   # run, copy results/ back here
#   deploy/reproduce-on-host.sh check   # clean-room: test + run, diff against the committed results/
set -euo pipefail

mode="${1:?usage: reproduce-on-host.sh adopt|check}"
cd "$(dirname "$0")/.."
[[ -f deploy/.env.deploy ]] && source deploy/.env.deploy
: "${LADING_SSH:?set LADING_SSH=user@host}"

ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10)
[[ -n "${LADING_SSH_KEY:-}" ]] && ssh_opts+=(-i "$LADING_SSH_KEY" -o IdentitiesOnly=yes)
remote() { ssh "${ssh_opts[@]}" "$LADING_SSH" "$@"; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git bundle create "$work/lading.bundle" HEAD 2>/dev/null
commit="$(git rev-parse --short HEAD)"

echo "→ shipping $commit to $LADING_SSH"
remote "rm -rf lading-repro && mkdir -p lading-repro"
scp -q "${ssh_opts[@]}" "$work/lading.bundle" "$LADING_SSH:lading-repro/"

tests=""
[[ "$mode" == "check" ]] && tests="uv run pytest -q -p no:warnings &&"
echo "→ fresh clone, uv sync --frozen, ${mode} (this takes several minutes)"
remote "cd lading-repro && docker run --rm -e LADING_WORKERS=${LADING_WORKERS:-4} -v \"\$PWD\":/w -w /w python:3.11.11-slim-bookworm sh -c '
  apt-get update -qq >/dev/null && apt-get install -y -qq git >/dev/null &&
  git config --global --add safe.directory \"*\" &&
  git clone -q lading.bundle repo && cd repo &&
  pip install -q --root-user-action=ignore uv==0.12.5 &&
  uv sync --frozen -q &&
  $tests uv run python -m evaluation.harness reproduce &&
  chown -R $(remote id -u):$(remote id -g) /w'"

mkdir -p "$work/results"
rsync -az -e "ssh ${ssh_opts[*]}" "$LADING_SSH:lading-repro/repo/results/" "$work/results/"

if [[ "$mode" == "adopt" ]]; then
  cp "$work"/results/*.json results/
  echo "results/ replaced with the deploy-host run of $commit"
  exit 0
fi

status=0
for f in results/*.json; do
  name="$(basename "$f")"
  [[ "$name" == "timings.json" ]] && continue
  if cmp -s "$f" "$work/results/$name"; then
    echo "identical  $name"
  else
    echo "DIFFERENT  $name"
    status=1
  fi
done
exit $status
