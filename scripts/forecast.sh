#!/bin/bash
# QuorumReach — Quorum Forecaster (Foundry/bash port, v2.0.0).
#
# Predicts whether a governance proposal will reach quorum before its
# voting deadline closes. Reads the proposal's current vote tallies
# and the live block head via `cast`, then projects the final turnout
# using a linear extrapolation (or a history mean if voting just
# started). Emits a single label (MISSED / UNLIKELY / REACH_QUORUM /
# LIKELY / GUARANTEED) plus a confidence score.
#
# Three modes:
#   onchain   — query an on-chain OpenZeppelin Governor or Compound
#               Bravo governor via `cast call`. Default.
#   demo      — synthetic forecast, no cast or RPC needed.
#   snapshot  — stub (the user can extend this with a Snapshot Hub
#               GraphQL query).
#
# Usage:
#   bash scripts/forecast.sh --governor 0xADDR --proposal-id N [--chain mainnet]
#   bash scripts/forecast.sh --mode demo
#   bash scripts/forecast.sh --mode snapshot --space ethereum.eth --proposal-id 0x...
#   bash scripts/forecast.sh --help

set -euo pipefail

# -------- Foundry required (after arg parsing so --help works offline) --------
ensure_cast() {
  if ! command -v cast >/dev/null 2>&1; then
    echo "Error: 'cast' not found. Install Foundry:" >&2
    echo "  curl -L https://foundry.paradigm.xyz | bash && foundryup" >&2
    exit 1
  fi
}

# -------- load network config from assets/networks.json --------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NET_JSON="$SCRIPT_DIR/../assets/networks.json"
[ ! -f "$NET_JSON" ] && { echo "Error: $NET_JSON not found"; exit 1; }

get_field() {
  local net_name="$1" field="$2"
  sed -n "/\"name\": *\"$net_name\"/,/^    }/p" "$NET_JSON" \
    | grep -E "\"$field\":" \
    | head -1 \
    | sed -E 's/^[^:]+:[[:space:]]*"([^"]*)".*/\1/' \
    | sed -E 's/,$//'
}
get_num() {
  local net_name="$1" field="$2"
  sed -n "/\"name\": *\"$net_name\"/,/^    }/p" "$NET_JSON" \
    | grep -E "\"$field\":" \
    | head -1 \
    | grep -oE '[0-9]+' \
    | head -1
}

# -------- OpenZeppelin Governor + Compound Bravo selectors --------
# OZ: state, proposalVotes, proposalSnapshot, proposalDeadline, quorum
SEL_OZ_STATE="0x3e4f49e6"
SEL_OZ_VOTES="0xda95691a"   # (against, for, abstain)
SEL_OZ_SNAPSHOT="0x462aca47"
SEL_OZ_DEADLINE="0x2e03ce1b"
SEL_OZ_QUORUM="0xf8ce5601"  # quorum(uint256 blockNumber)
# Bravo: proposals(uint256), state(uint256), quorumVotes()
SEL_BRAVO_PROPOSALS="0x7d5d6a93"
SEL_BRAVO_STATE="0x3e4f49e6"
SEL_BRAVO_QUORUM="0x973ab343"

# -------- arg parsing --------
MODE="onchain"
CHAIN="mainnet"
GOVERNOR=""
PROPOSAL_ID=""
LOOKBACK=5
QUORUM_OVERRIDE=""
JSON_OUT=0
PRINT_HELP=0
PREV=""

for arg in "$@"; do
  case "$PREV" in
    --mode)          MODE="$arg"; PREV=""; continue ;;
    --chain)         CHAIN="$arg"; PREV=""; continue ;;
    --governor)      GOVERNOR="$arg"; PREV=""; continue ;;
    --proposal-id)   PROPOSAL_ID="$arg"; PREV=""; continue ;;
    --lookback)      LOOKBACK="$arg"; PREV=""; continue ;;
    --quorum-absolute) QUORUM_OVERRIDE="$arg"; PREV=""; continue ;;
  esac
  case "$arg" in
    -h|--help)       PRINT_HELP=1 ;;
    --mode)          PREV="--mode" ;;
    --chain)         PREV="--chain" ;;
    --governor)      PREV="--governor" ;;
    --proposal-id)   PREV="--proposal-id" ;;
    --lookback)      PREV="--lookback" ;;
    --quorum-absolute) PREV="--quorum-absolute" ;;
    --json)          JSON_OUT=1 ;;
    -*)              echo "Unknown flag: $arg" >&2; exit 1 ;;
    *)               echo "Unexpected positional: $arg" >&2; exit 1 ;;
  esac
done
[ -n "$PREV" ] && { echo "Error: $PREV requires a value" >&2; exit 1; }

# -------- early-exits (no cast needed) --------
if [ "$PRINT_HELP" = "1" ]; then
  cat <<'USAGE'
QuorumReach — Quorum Forecaster (Foundry/bash port, v2.0.0)

Predicts whether a governance proposal will reach quorum before its
voting deadline closes. Three modes:

  onchain   Query an on-chain OpenZeppelin Governor or Compound
            Bravo governor via `cast call`. Default mode.
  demo      Synthetic forecast, no cast or RPC needed.
  snapshot  (Stub) Extend with a Snapshot Hub GraphQL query.

Usage:
  bash scripts/forecast.sh --mode onchain \\
    --governor 0xADDR --proposal-id N \\
    [--chain mainnet|testnet] \\
    [--lookback N] [--quorum-absolute N] \\
    [--json]
  bash scripts/forecast.sh --mode demo [--json]
  bash scripts/forecast.sh --help

Flags:
  --mode <onchain|demo|snapshot>  Forecasting mode (default: onchain)
  --governor 0xADDR               On-chain governor contract address
  --proposal-id N                 Proposal id (uint256)
  --chain <mainnet|testnet>        Pharos chain to read from (default: mainnet)
  --lookback N                    Number of past proposals to use for soft cap (default: 5)
  --quorum-absolute N             Override the on-chain quorum (raw token units)
  --json                          Output as JSON (for agent consumption)
  -h, --help                      Show this help

Prerequisites:
  - Foundry (cast): curl -L https://foundry.paradigm.xyz | bash && foundryup
  - jq: optional, only for --json pretty-printing
USAGE
  exit 0
fi

# Validate mode and required args
case "$MODE" in
  onchain)
    if [ -z "$GOVERNOR" ]; then
      echo "Error: --governor is required for onchain mode" >&2
      exit 1
    fi
    if [ -z "$PROPOSAL_ID" ]; then
      echo "Error: --proposal-id is required for onchain mode" >&2
      exit 1
    fi
    if [[ ! "$GOVERNOR" =~ ^0x[0-9a-fA-F]{40}$ ]]; then
      echo "Error: --governor must be 0x-prefixed 20-byte hex" >&2
      exit 1
    fi
    if ! [[ "$PROPOSAL_ID" =~ ^[0-9]+$ ]]; then
      echo "Error: --proposal-id must be a non-negative integer" >&2
      exit 1
    fi
    ;;
  demo)
    : # no args required
    ;;
  snapshot)
    echo "Error: snapshot mode is a stub in this version; the user can extend it" >&2
    echo "  with a Snapshot Hub GraphQL query. Use --mode onchain for now." >&2
    exit 1
    ;;
  *)
    echo "Error: unknown mode: $MODE (use 'onchain', 'demo', or 'snapshot')" >&2
    exit 1
    ;;
esac

# -------- resolve chain (only for onchain) --------
if [ "$MODE" = "onchain" ]; then
  case "$CHAIN" in
    mainnet) RPC_URL=$(get_field "mainnet" "rpcUrl"); EXPLORER_URL=$(get_field "mainnet" "explorerUrl"); CHAIN_ID=$(get_num "mainnet" "chainId"); NATIVE=$(get_field "mainnet" "nativeToken") ;;
    testnet) RPC_URL=$(get_field "atlantic-testnet" "rpcUrl"); EXPLORER_URL=$(get_field "atlantic-testnet" "explorerUrl"); CHAIN_ID=$(get_num "atlantic-testnet" "chainId"); NATIVE=$(get_field "atlantic-testnet" "nativeToken") ;;
    *) echo "Unknown chain: $CHAIN (use 'mainnet' or 'testnet')" >&2; exit 1 ;;
  esac
fi

# -------- demo mode: synthetic forecast, no cast --------
if [ "$MODE" = "demo" ]; then
  if [ "$JSON_OUT" = "1" ]; then
    cat <<'JSON'
{"type":"quorum_forecast","mode":"demo","governor":"0xGovernorOnPharos","governor_name":"openzeppelin-governor","chain_id":1672,"proposal":{"proposal_id":"42","for_votes":1800000,"against_votes":50000,"abstain_votes":10000,"current_total":1860000,"quorum":4000000,"start_block":9800000,"end_block":9800100,"state":1},"forecast":{"label":"REACH_QUORUM","confidence":0.55,"ratio":0.875,"projected_total":3720000,"quorum":4000000,"current_total":1860000,"elapsed_fraction":0.50,"time_remaining":50,"model":"linear","explanation":"Linear extrapolation from 50.0% elapsed. Synthetic demo data."},"history_used":6}
JSON
    exit 0
  fi
  cat <<'TXT'
========================================================================
  QUORUM FORECAST — openzeppelin-governor  (0xGovernorOnPharos)
  Proposal id: 42
========================================================================

  Current votes
    for:      1,800,000
    against:  50,000
    abstain:  10,000
    total:    1,860,000

  Quorum threshold:    4,000,000
  Elapsed:             50.0%
  Time remaining:      50
  Model:               linear (synthetic demo)

  >>> PROJECTED FINAL:  3,720,000  <<<
  >>> RATIO:            0.930            <<<
  >>> FORECAST:         REACH_QUORUM  (conf 0.55)  <<<

  Explanation: Linear extrapolation from 50.0% elapsed. Synthetic demo data.

  History used:  6 past proposal(s)

  ℹ️  This is a synthetic forecast for testing. Use --mode onchain with
  --governor 0xADDR --proposal-id N to forecast a real proposal.
========================================================================
TXT
  exit 0
fi

# -------- onchain mode: cast is required from here --------
ensure_cast

# -------- helpers --------

# Pad a 20-byte address to 32 bytes (for ABI encoding)
addr_padded() {
  local addr="${1#0x}"
  addr="${addr,,}"
  printf '0x%064s' "$addr"
}

# Pad a uint256
uint_padded() {
  printf '0x%064x' "$1"
}

# Decode a single-word uint256 hex (0x...) to decimal
hex_to_dec() {
  local h="${1#0x}"
  if [ -z "$h" ] || [ "$h" = "0" ] || [ "$h" = "0000000000000000000000000000000000000000000000000000000000000000" ]; then
    echo "0"
    return
  fi
  cast --to-dec "0x$h" 2>/dev/null || echo "0"
}

# -------- read OZ Governor state --------
read_oz_state() {
  local governor="$1"
  local pid="$2"
  local pid_padded
  pid_padded=$(uint_padded "$pid")

  # state(uint256) -> uint8
  local state_hex
  state_hex=$(cast call --rpc-url "$RPC_URL" "$governor" "state(uint256)(uint8)" "$pid" 2>/dev/null | tr -d '[:space:]' || true)
  if [ -z "$state_hex" ]; then
    echo "  ❌ governor call returned empty — is the address a real OZ Governor?" >&2
    echo "     Tried: cast call $governor \"state(uint256)(uint8)\" $pid" >&2
    return 1
  fi

  # proposalVotes(uint256) -> (uint256 against, uint256 for, uint256 abstain)
  local votes_raw
  votes_raw=$(cast call --rpc-url "$RPC_URL" "$governor" "proposalVotes(uint256)(uint256,uint256,uint256)" "$pid" 2>/dev/null | tr -d '[:space:]' || true)
  if [ -z "$votes_raw" ]; then
    echo "  ❌ proposalVotes call returned empty" >&2
    return 1
  fi
  # votes_raw is 0x + 3 * 64 hex chars
  local against_hex="${votes_raw:2:64}"
  local for_hex="${votes_raw:66:64}"
  local abstain_hex="${votes_raw:130:64}"
  local against_v for_v abstain_v
  against_v=$(hex_to_dec "$against_hex")
  for_v=$(hex_to_dec "$for_hex")
  abstain_v=$(hex_to_dec "$abstain_hex")

  # proposalSnapshot(uint256) -> uint256
  local start_hex
  start_hex=$(cast call --rpc-url "$RPC_URL" "$governor" "proposalSnapshot(uint256)(uint256)" "$pid" 2>/dev/null | tr -d '[:space:]' || true)
  # proposalDeadline(uint256) -> uint256
  local end_hex
  end_hex=$(cast call --rpc-url "$RPC_URL" "$governor" "proposalDeadline(uint256)(uint256)" "$pid" 2>/dev/null | tr -d '[:space:]' || true)

  local start_b end_b
  start_b=$(hex_to_dec "$start_hex")
  end_b=$(hex_to_dec "$end_hex")

  # quorum(uint256 blockNumber) -> uint256
  # Use end_block as a stable snapshot point; fall back to current head.
  local head_b quorum_b
  head_b=$(cast block-number --rpc-url "$RPC_URL" 2>/dev/null | tr -d '[:space:]' || echo "0")
  head_b=$(hex_to_dec "$head_b")
  local q_blk=$end_b
  [ "$q_blk" = "0" ] && q_blk=$head_b
  local quorum_hex
  quorum_hex=$(cast call --rpc-url "$RPC_URL" "$governor" "quorum(uint256)(uint256)" "$q_blk" 2>/dev/null | tr -d '[:space:]' || true)
  quorum_b=$(hex_to_dec "$quorum_hex")

  cat <<EOF
state=$state_hex
for=$for_v
against=$against_v
abstain=$abstain_v
start=$start_b
end=$end_b
quorum=$quorum_b
head=$head_b
EOF
  return 0
}

# -------- classify ratio -> label + confidence --------
classify() {
  local ratio="$1"
  # Use awk for float comparison
  awk -v r="$ratio" 'BEGIN {
    if (r < 0.25)  { print "MISSED 0.90"; exit }
    if (r < 0.75)  { print "UNLIKELY 0.70"; exit }
    if (r < 1.00)  { print "REACH_QUORUM 0.55"; exit }
    if (r < 1.30)  { print "LIKELY 0.75"; exit }
    print "GUARANTEED 0.90"
  }'
}

# -------- main onchain flow --------
PROP_DATA=$(read_oz_state "$GOVERNOR" "$PROPOSAL_ID") || exit 1

# Parse
FOR_V=$(echo "$PROP_DATA"   | awk -F= '/^for=/      {print $2}')
AGAINST_V=$(echo "$PROP_DATA" | awk -F= '/^against=/  {print $2}')
ABSTAIN_V=$(echo "$PROP_DATA" | awk -F= '/^abstain=/  {print $2}')
START_B=$(echo "$PROP_DATA"  | awk -F= '/^start=/    {print $2}')
END_B=$(echo "$PROP_DATA"    | awk -F= '/^end=/      {print $2}')
QUORUM_B=$(echo "$PROP_DATA" | awk -F= '/^quorum=/   {print $2}')
HEAD_B=$(echo "$PROP_DATA"   | awk -F= '/^head=/     {print $2}')
STATE_ID=$(echo "$PROP_DATA" | awk -F= '/^state=/    {print $2}')

# Apply quorum override
if [ -n "$QUORUM_OVERRIDE" ]; then
  QUORUM_B="$QUORUM_OVERRIDE"
fi

# Current totals
CURRENT_TOTAL=$((FOR_V + AGAINST_V + ABSTAIN_V))

# Elapsed fraction (block-based)
if [ -z "$START_B" ] || [ -z "$END_B" ] || [ "$END_B" -le "$START_B" ]; then
  ELAPSED=0
  REMAINING=0
else
  if [ "$HEAD_B" -lt "$START_B" ]; then
    ELAPSED="0.000"
  elif [ "$HEAD_B" -ge "$END_B" ]; then
    ELAPSED="1.000"
  else
    # float division: bash doesn't do floats; use awk
    ELAPSED=$(awk -v h="$HEAD_B" -v s="$START_B" -v e="$END_B" 'BEGIN { printf "%.4f", (h - s) / (e - s) }')
  fi
  REMAINING=$((END_B - HEAD_B))
  [ "$REMAINING" -lt 0 ] && REMAINING=0
fi

# Projection
EXPLANATION=""
if awk -v e="$ELAPSED" 'BEGIN { exit !(e < 0.001) }'; then
  # Voting just started
  if [ "$LOOKBACK" -gt 0 ]; then
    # We don't index VoteCast events, so we can't compute a true history mean.
    # Be honest in the explanation: history is currently a stub.
    PROJECTED=$CURRENT_TOTAL
    MODEL="no-data"
    EXPLANATION="Voting just started; linear extrapolation would divide by ~0. Falling back to current votes. (History mean is a stub in this version — pass --lookback 0 to silence this.)"
  else
    PROJECTED=$CURRENT_TOTAL
    MODEL="no-data"
    EXPLANATION="Voting just started; no historical data; projection equals current votes."
  fi
else
  PROJECTED=$(awk -v c="$CURRENT_TOTAL" -v e="$ELAPSED" 'BEGIN { printf "%d", c / e }')
  MODEL="linear"
  EXPLANATION=$(printf "Linear extrapolation from %.1f%% elapsed." "$(awk -v e="$ELAPSED" 'BEGIN { print e * 100 }')")
fi

# Ratio
if [ "$QUORUM_B" -le 0 ]; then
  LABEL="UNKNOWN"
  CONFIDENCE="0.00"
  RATIO="0.000"
  EXPLANATION="Quorum threshold unknown. Pass --quorum-absolute or check the governor."
else
  RATIO=$(awk -v p="$PROJECTED" -v q="$QUORUM_B" 'BEGIN { printf "%.3f", p / q }')
  CLASSIFY_RESULT=$(classify "$RATIO")
  LABEL=$(echo "$CLASSIFY_RESULT" | awk '{print $1}')
  CONFIDENCE=$(echo "$CLASSIFY_RESULT" | awk '{print $2}')
fi

# -------- output --------
GOVERNOR_NAME="openzeppelin-governor"

if [ "$JSON_OUT" = "1" ]; then
  jq -n \
    --arg type "quorum_forecast" \
    --arg mode "onchain" \
    --arg governor "$GOVERNOR" \
    --arg gname "$GOVERNOR_NAME" \
    --argjson chain_id "$CHAIN_ID" \
    --arg pid "$PROPOSAL_ID" \
    --argjson for_v "$FOR_V" \
    --argjson against_v "$AGAINST_V" \
    --argjson abstain_v "$ABSTAIN_V" \
    --argjson current "$CURRENT_TOTAL" \
    --argjson quorum "$QUORUM_B" \
    --argjson start_b "$START_B" \
    --argjson end_b "$END_B" \
    --argjson state_id "$STATE_ID" \
    --arg label "$LABEL" \
    --arg conf "$CONFIDENCE" \
    --arg ratio "$RATIO" \
    --argjson projected "$PROJECTED" \
    --argjson current_total "$CURRENT_TOTAL" \
    --arg elapsed "$ELAPSED" \
    --argjson remaining "$REMAINING" \
    --arg model "$MODEL" \
    --arg expl "$EXPLANATION" \
    --arg explorer "${EXPLORER_URL}/address/${GOVERNOR}" \
    '{
      type: $type,
      mode: $mode,
      governor: $governor,
      governor_name: $gname,
      chain_id: $chain_id,
      proposal: {
        proposal_id: $pid,
        for_votes: $for_v,
        against_votes: $against_v,
        abstain_votes: $abstain_v,
        current_total: $current_total,
        quorum: $quorum,
        start_block: $start_b,
        end_block: $end_b,
        state: $state_id,
        explorer: $explorer
      },
      forecast: {
        label: $label,
        confidence: ($conf | tonumber),
        ratio: ($ratio | tonumber),
        projected_total: $projected,
        quorum: $quorum,
        current_total: $current_total,
        elapsed_fraction: ($elapsed | tonumber),
        time_remaining: $remaining,
        model: $model,
        explanation: $expl
      },
      history_used: 0
    }'
  exit 0
fi

cat <<TXT
========================================================================
  QUORUM FORECAST — $GOVERNOR_NAME  ($GOVERNOR)
  Proposal id: $PROPOSAL_ID
  Chain:       $CHAIN (id $CHAIN_ID)
========================================================================

  Current votes
    for:      $(printf "%'d" "$FOR_V")
    against:  $(printf "%'d" "$AGAINST_V")
    abstain:  $(printf "%'d" "$ABSTAIN_V")
    total:    $(printf "%'d" "$CURRENT_TOTAL")

  Quorum threshold:    $(printf "%'d" "$QUORUM_B")
  Elapsed:             $(awk -v e="$ELAPSED" 'BEGIN { printf "%.1f%%", e * 100 }')
  Time remaining:      $(printf "%'d" "$REMAINING") blocks
  Model:               $MODEL

  >>> PROJECTED FINAL:  $(printf "%'d" "$PROJECTED")  <<<
  >>> RATIO:            $RATIO            <<<
  >>> FORECAST:         $LABEL  (conf $CONFIDENCE)  <<<

  Explanation: $EXPLANATION

  Explorer: ${EXPLORER_URL}/address/$GOVERNOR
========================================================================
TXT
