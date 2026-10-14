#!/usr/bin/env bash
# Ship the API to the VPS over SSH. Safe to re-run: rsync is incremental, compose only recreates what
# changed, and the proxy site block is added once and validated before any reload.
#
# Settings come from the environment or an untracked deploy/.env.deploy:
#   LADING_SSH        user@host                         (required)
#   LADING_SSH_KEY    path to the private key            (optional)
#   API_DOMAIN        hostname for the API               (default <ip-with-dashes>.sslip.io)
#   ALLOWED_ORIGINS   comma list for CORS                (required: Vercel URL,http://localhost:5173)
#   EDGE_MODE         standalone | shared                (default standalone)
#   EDGE_NETWORK      existing proxy network, shared mode
#   EDGE_CADDY        existing proxy container, shared mode
#   EDGE_CADDYFILE    host path of that proxy's Caddyfile, shared mode
#   REMOTE_DIR        where the bundle lives             (default ~/lading)
set -euo pipefail

cd "$(dirname "$0")/.."
[[ -f deploy/.env.deploy ]] && source deploy/.env.deploy

: "${LADING_SSH:?set LADING_SSH=user@host}"
: "${ALLOWED_ORIGINS:?set ALLOWED_ORIGINS}"
host="${LADING_SSH#*@}"
API_DOMAIN="${API_DOMAIN:-${host//./-}.sslip.io}"
EDGE_MODE="${EDGE_MODE:-standalone}"
REMOTE_DIR="${REMOTE_DIR:-lading}"
COMMIT="$(git rev-parse --short HEAD)"

ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10)
[[ -n "${LADING_SSH_KEY:-}" ]] && ssh_opts+=(-i "$LADING_SSH_KEY" -o IdentitiesOnly=yes)
remote() { ssh "${ssh_opts[@]}" "$LADING_SSH" "$@"; }

if [[ -n "$(git status --porcelain -- . ':(exclude)scenarios/curated/index.json' ':(exclude)web')" ]]; then
  echo "refusing to deploy a dirty tree; commit first" >&2
  exit 1
fi

echo "→ syncing $COMMIT to $LADING_SSH:$REMOTE_DIR"
remote "mkdir -p $REMOTE_DIR"
rsync -az --delete -e "ssh ${ssh_opts[*]}" \
  --exclude .git --exclude .venv --exclude web --exclude internal --exclude 'scenarios/generated' \
  --exclude '.ci-results' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.mypy_cache' \
  --exclude '.ruff_cache' --exclude 'deploy/.env.deploy' \
  ./ "$LADING_SSH:$REMOTE_DIR/"

compose="docker compose -f deploy/docker-compose.yml"
env_line="LADING_COMMIT=$COMMIT ALLOWED_ORIGINS='$ALLOWED_ORIGINS' API_DOMAIN='$API_DOMAIN'"
if [[ "$EDGE_MODE" == "shared" ]]; then
  : "${EDGE_NETWORK:?shared mode needs EDGE_NETWORK}" "${EDGE_CADDY:?shared mode needs EDGE_CADDY}" "${EDGE_CADDYFILE:?shared mode needs EDGE_CADDYFILE}"
  subnet="$(remote "docker network inspect $EDGE_NETWORK --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}'")"
  env_line="$env_line EDGE_NETWORK=$EDGE_NETWORK TRUSTED_PROXIES=$subnet"
  compose="$compose -f deploy/compose.shared-edge.yml"
else
  compose="$compose --profile standalone"
fi

echo "→ building and starting containers"
remote "cd $REMOTE_DIR && $env_line $compose up -d --build --remove-orphans"

if [[ "$EDGE_MODE" == "shared" ]]; then
  echo "→ routing $API_DOMAIN through $EDGE_CADDY"
  remote "API_DOMAIN='$API_DOMAIN' EDGE_CADDY='$EDGE_CADDY' EDGE_CADDYFILE='$EDGE_CADDYFILE' bash -s" <<'REMOTE'
set -euo pipefail
marker="# lading api (managed by lading/deploy/deploy-api.sh)"
if ! grep -qF "$marker" "$EDGE_CADDYFILE"; then
  cp "$EDGE_CADDYFILE" "$EDGE_CADDYFILE.bak-lading"
  printf '\n%s\n%s {\n\tencode gzip\n\treverse_proxy lading-api:8000\n}\n' "$marker" "$API_DOMAIN" >> "$EDGE_CADDYFILE"
  if ! docker exec "$EDGE_CADDY" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
    cp "$EDGE_CADDYFILE.bak-lading" "$EDGE_CADDYFILE"
    echo "proxy config failed validation; restored the original" >&2
    exit 1
  fi
fi
docker exec "$EDGE_CADDY" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
REMOTE
fi

echo "→ waiting for https://$API_DOMAIN/health"
for _ in $(seq 1 30); do
  if curl -fsS "https://$API_DOMAIN/health" >/dev/null 2>&1; then
    curl -fsS "https://$API_DOMAIN/health"; echo
    echo "API live at https://$API_DOMAIN ($COMMIT)"
    exit 0
  fi
  sleep 4
done
echo "API did not become healthy at https://$API_DOMAIN" >&2
remote "cd $REMOTE_DIR && docker compose -f deploy/docker-compose.yml logs --tail 50 api" >&2 || true
exit 1
