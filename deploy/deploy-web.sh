#!/usr/bin/env bash
# Build the console here and push the built output to Vercel with the CLI (--prebuilt), so the API URL
# is baked in from this machine and Vercel never builds from source. No git integration.
#   VITE_API_URL   /api (proxied by vercel.json to the VPS, the default) or an absolute HTTPS URL
set -euo pipefail

cd "$(dirname "$0")/.."
[[ -f deploy/.env.deploy ]] && source deploy/.env.deploy
: "${VITE_API_URL:?set VITE_API_URL to the API HTTPS URL}"
: "${API_DOMAIN:?set API_DOMAIN, the host vercel.json proxies /api to}"

cd web
# vercel.json is generated so the API host stays in the untracked deploy env, not in the repo.
sed "s#__LADING_API_DOMAIN__#$API_DOMAIN#g" vercel.template.json > vercel.json
npm ci --no-audit --no-fund
VITE_API_URL="$VITE_API_URL" vercel build --prod --yes
grep -rq "$VITE_API_URL" .vercel/output/static/assets || { echo "built bundle doesn't contain $VITE_API_URL" >&2; exit 1; }
vercel deploy --prebuilt --prod --yes
