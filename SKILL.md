---
name: quorum-forecaster
description: >
  REQUIRED for any task that requires predicting whether an on-chain or
  off-chain governance proposal will reach quorum before the voting
  deadline closes. Invoke when the user asks to "forecast quorum",
  "will this proposal pass", "quorum reach", "is this DAO vote going
  to make it", "voting projection", "governance forecast", or wants a
  per-proposal breakdown of (current votes, quorum threshold, time
  remaining, projected final votes, confidence). Use the bundled
  `src/quorum_forecast.py` engine to pull live proposal state via
  JSON-RPC (any EVM-compatible chain) and the Snapshot GraphQL API
  (off-chain governance).
  Do not attempt quorum forecasting without reading this skill.
version: 0.1.0
requires:
  - python >= 3.9
  - requests
  - anyBins:
      - cast   # optional, used for manual cross-check of proposal state
      - jq     # optional, used for ergonomic RPC URL extraction
author: Meenah57
bins: [python3]
tags: [pharos, blockchain, agent-skill]
agents: [claude, codex, gemini, openclaw]
---


# Quorum Forecaster

Predict whether a governance proposal will reach quorum before its
voting deadline closes. Works for:

- **On-chain governors** — Compound (Bravo), OpenZeppelin Governor,
  Tally-style custom governors, and Pharos-native governance.
- **Off-chain governors** — Snapshot (used by most DAOs that don't
  pay gas for voting).

The skill ships a Python engine that:

1. Detects the governor type (on-chain vs Snapshot) from the input.
2. Pulls the current vote tally, quorum threshold, and deadline.
3. Pulls the vote history of the last N proposals to learn the typical
   voting curve (front-loaded vs back-loaded vs linear).
4. Fits a curve to the *current* proposal's partial vote timeline and
   projects the final vote count at deadline.
5. Returns a labeled outcome: `MISSED`, `UNLIKELY`, `REACH_QUORUM`,
   `LIKELY`, `GUARANTEED`, plus a confidence 0–1.

## When to use

- The user asks "will proposal X reach quorum?"
- The user wants a single "quorum forecast" number for a list of
  active proposals.
- The user wants to know *when* the quorum threshold will be crossed
  (useful for vote-trolling / governance dashboards).
- The user wants to compare the projected turnout to past proposals
  on the same DAO.

## When NOT to use

- Snapshot proposals whose space is unknown — you'll need the
  `space` slug (e.g. `aave.eth`, `ens.eth`).
- DAOs that use a custom voting-escrow with a non-standard quorum
  (the engine supports a manual `--quorum-absolute` override).
- Snapshot proposals that are still in "pending" state (no votes
  recorded yet). Wait until the proposal goes active.

## Inputs

| Input              | Required | Description                                            |
|--------------------|----------|--------------------------------------------------------|
| `governor`         | yes      | Governor contract address (on-chain) OR Snapshot space |
| `proposal_id`      | yes      | Proposal id (on-chain) or Snapshot proposal id        |
| `rpc_url`          | depends  | JSON-RPC endpoint (required for on-chain governors)    |
| `mode`             | no       | `auto` (default), `onchain`, or `snapshot`             |
| `lookback`         | no       | How many past proposals to use for curve fitting (default 8) |
| `quorum_absolute`  | no       | Override quorum threshold (decimal token units)        |
| `format`           | no       | `text` (default), `json`, `markdown`, `html`           |

## Outputs

A structured report with:

- Current `for`, `against`, `abstain` vote totals.
- Quorum threshold (and source — on-chain read vs supplied override).
- Time remaining until deadline.
- Projected final vote total.
- **Forecast label** + confidence 0–1.
- A short human-readable explanation.

### Forecast labels

| Label          | Meaning                                                       |
|----------------|---------------------------------------------------------------|
| `MISSED`       | Projected final < 25% of quorum. Proposal will fail.          |
| `UNLIKELY`     | Projected final < 75% of quorum. Proposal almost certainly fails. |
| `REACH_QUORUM` | Projected final between 75% and 100% of quorum. Could go either way. |
| `LIKELY`       | Projected final between 100% and 130% of quorum. Should pass. |
| `GUARANTEED`   | Projected final > 130% of quorum. Already locked in.          |

## Quick start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Forecast an on-chain governor proposal (Pharos mainnet)
python src/quorum_forecast.py \
  --governor 0xGovernorContract \
  --proposal-id 42 \
  --rpc-url https://rpc.pharos.xyz

# 3. Forecast a Snapshot proposal
python src/quorum_forecast.py \
  --governor aave.eth \
  --proposal-id 0xabc123... \
  --mode snapshot

# 4. Get a JSON report
python src/quorum_forecast.py \
  --governor 0xGovernorContract \
  --proposal-id 42 \
  --rpc-url https://rpc.pharos.xyz \
  --format json > forecast.json
```

## Agent invocation pattern

When the user asks for a quorum forecast, the Agent should:

1. Determine whether the proposal is on-chain or Snapshot. If unclear,
   ask the user; the heuristic is "did the user supply a 0x address
   for the governor?" — yes means on-chain.
2. Resolve the RPC URL from the chain the user mentions (e.g. Pharos
   mainnet → `https://rpc.pharos.xyz`).
3. Run `src/quorum_forecast.py` with the parameters above.
4. Surface the forecast label, confidence, and time remaining as the
   top of the response. Optionally pipe through `src/report.py` for a
   formatted report.

## Error handling

| Error                       | Cause                                  | Action |
|-----------------------------|----------------------------------------|--------|
| `unknown governor type`     | Contract doesn't match known patterns  | Use `--mode onchain` + `--quorum-absolute` |
| `proposal not found`        | Bad proposal id                        | Verify proposal id via block explorer |
| `voting not started`        | Proposal still pending                 | Tell the user, ask for a later check |
| `voting already ended`      | Past deadline                          | Return the final vote count instead of forecast |
| `snapshot api timeout`      | Snapshot hub down                      | Retry, or fall back to manual tally |

## Limitations

- The forecaster assumes the historical voting curve of the DAO is a
  reasonable prior for the current proposal. Sudden shifts in turnout
  (e.g. an airdrop announcement) won't be detected.
- For very long voting periods (>2 weeks), curve fit degrades; the
  engine caps `--lookback` and falls back to linear extrapolation.
- Snapshot proposals with quorum computed as a percentage of total
  supply require a known supply; if the engine can't find one, the
  user must supply `--quorum-absolute`.

## Prerequisites

```bash
python3 --version   # 3.10+
```

The skill uses only the Python standard library (`urllib.request`,
`json`, `argparse`). No third-party packages, no Foundry, no
`pip install` step.

The skill is **read-only** — no private key is required or accepted.

## Network Configuration

Network RPC URLs and chain IDs are sourced from
`assets/networks.json` (canonical Pharos Skill Engine schema). To
add a new network, append a new object to the `networks` array and
update `defaultNetwork` if needed.

## Capability Index

| User Need | Capability | Detailed Instructions |
|---|---|---|
| Default entry point | CLI with a `--wallet` / `--safe` / `--governor` flag | See the `Usage` section in the README; the CLI takes a target identifier and prints a Markdown or JSON report |
| JSON for an agent | `--format json` | Output is a structured payload that an agent can import directly |
| Markdown report | pipe to `report.py` | `python3 src/... --format json \| python3 src/report.py --format markdown --out X.md` |
| Bounded scan | `--max-blocks` / `--lookback` / `--block-count` | Default scans are bounded to stay within the public Pharos RPC's request rate |
| Network switch | `--chain mainnet\|testnet` | Default is Atlantic testnet; pass `--chain mainnet` to switch |

## General Error Handling

| Error Scenario | CLI Error Signature | Handling |
|---|---|---|
| Target not on the specified chain | `null` receipt / no data returned | Exit with "not found on chain=X; try `--chain <other>`" |
| RPC rate-limited (HTTP 429) | Backoff response from RPC | Built-in exponential backoff (0.4s, 0.8s, 1.6s, 3.2s) with 4 retry attempts |
| Bad target format | Validator rejects the input | CLI prints a usage hint; no RPC call is made |
| Missing required arg | `argparse` exits with usage | CLI prints required args; user re-invokes with the right flags |
| No matches (clean target) | Empty result / `verdict: clean` | Normal case — emit the "no issues" report, no error |

## Security Reminders

- **Private Key Protection** — the skill is read-only and never
  accepts a private key. Do not paste keys into chat.
- **Network Confirmation** — before any future write-skill
  integration, confirm the network with the user.
- **No External API** — the skill does not call any third-party
  service beyond the Pharos RPC and PharosScan (where applicable).
  All data is fetched directly.

## Write Operation Pre-checks

This skill is **read-only** and never submits a transaction, so the
full 4-step write pre-check is not applicable. If a future version
adds a write path, the pre-checks must include:

1. **Private Key Check** — `--private-key` / `$PRIVATE_KEY` must be
   set; warn if the key has zero balance.
2. **Derive Public Address** — `cast wallet address`; confirm the
   key is for the intended network.
3. **Network Confirmation** — prompt the user with "You are about
   to write to Pacific mainnet. Continue? (y/N)".
4. **Automatic Balance Check** — `cast balance`; if below the
   operation cost + gas, abort with a clear error.
