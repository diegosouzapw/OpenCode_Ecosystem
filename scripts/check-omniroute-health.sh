#!/usr/bin/env bash
# check-omniroute-health.sh
# Validates an OmniRoute tenant is healthy enough for the OpenCode Ecosystem.
#
# Usage:
#   bash scripts/check-omniroute-health.sh <BASE_URL> [API_KEY]
#
# Example:
#   bash scripts/check-omniroute-health.sh https://or.cx.com.br "$OMNIROUTE_API_KEY"
#
# Exit codes:
#   0  — tenant healthy, ready for integration
#   1  — minimum threshold not met (see message)
#   2  — connectivity error (DNS / network / 5xx)
#   3  — missing dependency (curl / jq)

set -euo pipefail

BASE_URL="${1:-}"
API_KEY="${2:-${OMNIROUTE_API_KEY:-}}"

# --- Dep check ---
for dep in curl jq; do
  if ! command -v "$dep" >/dev/null 2>&1; then
    echo "ERROR: '$dep' is required but not installed." >&2
    exit 3
  fi
done

if [ -z "$BASE_URL" ]; then
  echo "Usage: $0 <BASE_URL> [API_KEY]" >&2
  echo "Example: $0 https://or.cx.com.br \$OMNIROUTE_API_KEY" >&2
  exit 1
fi

# Strip trailing slash
BASE_URL="${BASE_URL%/}"

AUTH_HEADER=""
[ -n "$API_KEY" ] && AUTH_HEADER="Authorization: Bearer $API_KEY"

# --- Helper ---
fetch() {
  local path="$1"
  if [ -n "$AUTH_HEADER" ]; then
    curl -sf --max-time 10 -H "$AUTH_HEADER" "$BASE_URL$path"
  else
    curl -sf --max-time 10 "$BASE_URL$path"
  fi
}

# --- Check 1: /v1/models ---
echo -n "[1/4] /v1/models ... "
if ! MODELS_JSON=$(fetch /v1/models 2>&1); then
  echo "FAIL — connectivity error ($MODELS_JSON)"
  exit 2
fi
MODEL_COUNT=$(echo "$MODELS_JSON" | jq '.data | length')
if [ "$MODEL_COUNT" -lt 100 ]; then
  echo "FAIL — only $MODEL_COUNT models (expected ≥ 100)"
  exit 1
fi
echo "OK ($MODEL_COUNT models)"

# --- Check 2: /api/providers ---
echo -n "[2/4] /api/providers ... "
if ! PROV_JSON=$(fetch /api/providers 2>&1); then
  echo "WARN — endpoint unavailable (continuing)"
else
  ACTIVE_COUNT=$(echo "$PROV_JSON" | jq '[.[] | select(.testStatus == "active")] | length' 2>/dev/null || echo 0)
  if [ "$ACTIVE_COUNT" -lt 5 ]; then
    echo "FAIL — only $ACTIVE_COUNT active providers (expected ≥ 5)"
    exit 1
  fi
  echo "OK ($ACTIVE_COUNT active providers)"
fi

# --- Check 3: /api/combos ---
echo -n "[3/4] /api/combos ... "
if ! COMBOS_JSON=$(fetch /api/combos 2>&1); then
  echo "WARN — endpoint unavailable (continuing)"
else
  COMBO_COUNT=$(echo "$COMBOS_JSON" | jq 'length' 2>/dev/null || echo 0)
  if [ "$COMBO_COUNT" -lt 1 ]; then
    echo "WARN — no combos configured (auto-routing still works)"
  else
    echo "OK ($COMBO_COUNT combos)"
  fi
fi

# --- Check 4: /api/mcp/stream reachable ---
echo -n "[4/4] /api/mcp/stream ... "
HTTP_CODE=$(curl -s -o /dev/null --max-time 5 -w "%{http_code}" \
  ${AUTH_HEADER:+-H "$AUTH_HEADER"} \
  "$BASE_URL/api/mcp/stream" 2>/dev/null || echo "000")
# Anything < 500 is acceptable (4xx is expected without proper handshake)
if [ "$HTTP_CODE" -lt 500 ] && [ "$HTTP_CODE" != "000" ]; then
  echo "OK (HTTP $HTTP_CODE)"
else
  echo "WARN — HTTP $HTTP_CODE (MCP may be disabled on this tenant)"
fi

echo ""
echo "✓ OmniRoute tenant is healthy and ready for OpenCode Ecosystem integration."
echo "  Base URL: $BASE_URL"
echo "  Models:   $MODEL_COUNT"
[ -n "${ACTIVE_COUNT:-}" ] && echo "  Providers (active): $ACTIVE_COUNT"
[ -n "${COMBO_COUNT:-}" ] && echo "  Combos:   $COMBO_COUNT"
exit 0
