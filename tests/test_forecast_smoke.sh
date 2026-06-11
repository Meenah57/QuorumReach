#!/bin/bash
set -e
SCRIPT="scripts/forecast.sh"
bash "$SCRIPT" --help >/dev/null
if ! command -v cast >/dev/null 2>&1; then
  if bash "$SCRIPT --mode demo" 2>&1 | grep -q "GUARANTEED"; then
    echo "OK: demo mode works"
  else
    echo "FAIL: demo mode"; exit 1
  fi
else
  bash "$SCRIPT --mode demo" >/dev/null
  echo "OK: demo mode + cast installed"
fi
echo "All smoke tests passed."
