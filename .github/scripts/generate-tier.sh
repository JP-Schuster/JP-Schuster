#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TIER_DIR="${GITHUB_TIER_DIR:-$HOME/github-tier}"
OUTPUT="${STATS_OUTPUT:-$ROOT/assets/github-tier.svg}"
USERNAME="${GITHUB_USERNAME:-JP-Schuster}"
TOKEN="${GH_PAT:-${GITHUB_TOKEN:-}}"

if [[ -z "$TOKEN" ]]; then
  echo "GH_PAT or GITHUB_TOKEN is required" >&2
  exit 1
fi

if [[ ! -d "$TIER_DIR" ]]; then
  echo "github-tier directory not found at $TIER_DIR" >&2
  exit 1
fi

cd "$TIER_DIR"
if [[ ! -d node_modules ]]; then
  npx --yes pnpm@10 install
fi

PORT="${GITHUB_TIER_PORT:-3333}"
export GITHUB_TOKEN="$TOKEN"

npx tsx src/index.ts > /tmp/github-tier-local.log 2>&1 &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 30); do
  if curl -sf "http://localhost:${PORT}/api/tier?user=${USERNAME}&theme=tokyonight" | head -c 4 | grep -q "<svg"; then
    curl -sL "http://localhost:${PORT}/api/tier?user=${USERNAME}&theme=tokyonight" -o "$OUTPUT"
    echo "Generated $OUTPUT"
    exit 0
  fi
  sleep 1
done

echo "Failed to start github-tier server" >&2
cat /tmp/github-tier-local.log >&2 || true
exit 1
