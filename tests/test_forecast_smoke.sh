#!/bin/bash
# Smoke test for QuorumReach / Quorum Forecaster (Foundry/bash port, v2.0.0).
# Verifies the CLI parses, help text works offline, and error paths are clear.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
SCRIPT="$SKILL_DIR/scripts/forecast.sh"

PASS=0
FAIL=0

# run <name> <expected-substring> <args...>
run() {
  local name="$1"
  local expected="$2"
  shift 2
  local out
  out=$(bash "$SCRIPT" "$@" 2>&1 || true)
  if echo "$out" | grep -qF -- "$expected"; then
    echo "  OK: $name"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $name"
    echo "       expected substring: $expected"
    echo "       actual: $(echo "$out" | head -3)"
    FAIL=$((FAIL + 1))
  fi
}

echo "Test 1: --help works (no cast required)"
run "help text present" "QuorumReach" --help

echo "Test 2: --mode demo produces a forecast"
run "demo mode produces REACH_QUORUM" "FORECAST" --mode demo

echo "Test 3: --mode demo --json is valid JSON"
if bash "$SCRIPT" --mode demo --json 2>&1 | jq . >/dev/null 2>&1; then
  echo "  OK: demo JSON is valid"
  PASS=$((PASS + 1))
else
  echo "  FAIL: demo JSON is not valid"
  FAIL=$((FAIL + 1))
fi

echo "Test 4: unknown mode rejected"
run "unknown mode rejected" "unknown mode" --mode bogus

echo "Test 5: onchain mode requires --governor"
run "onchain requires --governor" "--governor is required" --mode onchain --proposal-id 42

echo "Test 6: onchain mode requires --proposal-id"
run "onchain requires --proposal-id" "--proposal-id is required" --mode onchain --governor 0x1234567890123456789012345678901234567890

echo "Test 7: bad governor address rejected"
run "bad governor rejected" "0x-prefixed 20-byte hex" \
  --mode onchain --governor not-hex --proposal-id 42

echo "Test 8: bad proposal-id rejected"
run "bad proposal-id rejected" "non-negative integer" \
  --mode onchain --governor 0x1234567890123456789012345678901234567890 --proposal-id abc

echo "Test 9: unknown flag rejected"
run "unknown flag rejected" "Unknown flag" --foo

echo "Test 10: bad chain rejected"
run "bad chain rejected" "Unknown chain" \
  --mode onchain --governor 0x1234567890123456789012345678901234567890 --proposal-id 42 --chain bogus

echo "Test 11: cast-missing error is clear (only when cast is not installed)"
if ! command -v cast >/dev/null 2>&1; then
  run "cast-missing error clear" "not found" \
    --mode onchain --governor 0x1234567890123456789012345678901234567890 --proposal-id 42
else
  echo "  SKIP: cast is installed"
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" = "0" ] || exit 1
