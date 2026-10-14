#!/usr/bin/env bash
# Build the console and push the built folder to Vercel with the CLI. No git integration.
#   VITE_API_URL   the API's HTTPS URL (required)
set -euo pipefail

cd "$(dirname "$0")/.."
[[ -f deploy/.env.deploy ]] && source deploy/.env.deploy
: "${VITE_API_URL:?set VITE_API_URL to the API's HTTPS URL}"

cd web
npm ci --no-audit --no-fund
VITE_API_URL="$VITE_API_URL" npm run build
vercel deploy --prod --yes
