---
name: QuorumReach
description: AI agent skill for predicting whether a governance proposal will reach quorum before its voting deadline closes. Works with OpenZeppelin Governor and Compound Bravo contracts via cast (Foundry), and can be extended for Snapshot. Use this skill whenever an agent needs to forecast a proposal outcome, time a vote, or assess a DAO's health. Triggers on phrases like "will this proposal pass", "quorum forecast", "governance vote predictor", "pharos governance", "OZ governor forecast", "compound bravo forecast".
version: 2.0.0
author: Meenah57
requires: read
bins: [bash, cast, jq, awk]
network: pharos
tags: [governance, quorum, voting, openzeppelin, compound-bravo, snapshot, pharos, foundry, bash]
agents: [claude, codex, gemini, openclaw]
---

# QuorumReach — Quorum Forecaster

A bash + cast (Foundry) skill that forecasts whether an on-chain governance proposal will reach quorum before its voting deadline closes. Three modes:

- **`onchain`** (default) — query an OpenZeppelin Governor or Compound Bravo contract via `cast call`
- **`demo`** — synthetic forecast, no cast or RPC needed
- **`snapshot`** — stub for Snapshot Hub GraphQL; extend it yourself

## How it scores

Let `elapsed = (head - start) / (end - start)` ∈ [0, 1].

| Case | Projection |
|---|---|
| `elapsed < 0.001` (voting just started) | current votes (history mean is a stub in this version) |
| `elapsed >= 0.001` | **linear extrapolation**: `projected = current / elapsed` |

| Ratio range | Label | Confidence |
|---|---|---|
| 0.00 – 0.25 | `MISSED` | 0.90 |
| 0.25 – 0.75 | `UNLIKELY` | 0.70 |
| 0.75 – 1.00 | `REACH_QUORUM` | 0.55 |
| 1.00 – 1.30 | `LIKELY` | 0.75 |
| 1.30+ | `GUARANTEED` | 0.90 |

## Quick Actions

### Forecast a real proposal
```
Will proposal 42 on OZ Governor 0xabc...def reach quorum on Pharos mainnet?
```

### Run the demo
```
Run the quorum forecaster demo
```

### Get the forecast as JSON
```
Forecast proposal 42 on Governor 0xabc... and return JSON
```

## Invocation

```bash
# On-chain forecast (default mode)
bash scripts/forecast.sh --mode onchain \
  --governor 0xGOVERNOR_ADDRESS --proposal-id 42 --chain mainnet

# Demo
bash scripts/forecast.sh --mode demo

# JSON output
bash scripts/forecast.sh --mode onchain --governor 0xADDR --proposal-id 42 --json

# Override the quorum
bash scripts/forecast.sh --mode onchain --governor 0xADDR --proposal-id 42 \
  --quorum-absolute 4000000
```

## Flags

| Flag | Description |
|---|---|
| `--mode <onchain \| demo \| snapshot>` | Forecasting mode (default: onchain) |
| `--governor 0xADDR` | On-chain governor contract address (required for onchain) |
| `--proposal-id N` | Proposal id as a non-negative integer (required for onchain) |
| `--chain <mainnet \| testnet>` | Pharos chain to read from (default: mainnet) |
| `--lookback N` | Number of past proposals to use for soft cap (default: 5; history mean is currently a stub) |
| `--quorum-absolute N` | Override the on-chain quorum (raw token units) |
| `--json` | Output as JSON (for agent consumption) |
| `-h`, `--help` | Show the help text |

## Supported governors

**OpenZeppelin Governor** (default — read by `--mode onchain`):

| Function | Selector |
|---|---|
| `state(uint256)` | `0x3e4f49e6` |
| `proposalVotes(uint256)` | `0xda95691a` |
| `proposalSnapshot(uint256)` | `0x462aca47` |
| `proposalDeadline(uint256)` | `0x2e03ce1b` |
| `quorum(uint256)` | `0xf8ce5601` |

**Compound Bravo** (`GovernorAlpha` / `GovernorBravo`) — supported; pass `--mode onchain` and the script auto-detects the ABI. See `references/governors.md` for the Bravo selectors.

**Snapshot** (off-chain) — stub in this version. Extend the script with a Snapshot Hub GraphQL query against `https://hub.snapshot.org/graphql`.

## Networks

| Network | Chain ID | RPC URL |
|---|---:|---|
| mainnet (Pacific Ocean) | 1672 | `https://rpc.pharos.xyz` |
| atlantic-testnet | 688689 | `https://atlantic.dplabs-internal.com` |

Chain config is read from `assets/networks.json` at startup. Edit that file to add private RPC endpoints.

## Dependencies

- **Foundry** (gives you `cast`) — install with `curl -L https://foundry.paradigm.xyz | bash && foundryup`
- **bash 4+** — preinstalled on macOS, Ubuntu 20+, most Linux
- **awk** — preinstalled on every Unix (used for float math)
- **jq** — required only for `--json` output

## Security model

- The skill is **read-only** — it never imports, reads, or stores a private key.
- It reads governance state via `eth_call` (read-only RPC) — it cannot move funds or vote on proposals.
- It never submits a transaction, never writes to disk, never phones home.
- The only network call is to the user-configured RPC URL (or the Snapshot Hub GraphQL endpoint, if you extend the snapshot mode).

## Error handling

- Missing cast → "Error: 'cast' not found. Install Foundry..."
- Unknown mode → "Error: unknown mode: bogus (use 'onchain', 'demo', or 'snapshot')"
- Missing `--governor` / `--proposal-id` for onchain → clear error + usage hint
- Bad address / bad proposal id → format error
- Bad chain → "Unknown chain: bogus (use 'mainnet' or 'testnet')"
- Cast returns empty for `state(proposalId)` → "governor call returned empty — is the address a real OZ Governor?"

## Reference docs

- `references/forecasting-model.md` — the math behind the label thresholds and the linear extrapolation
- `references/governors.md` — the supported OZ Governor / Compound Bravo / Snapshot interfaces, function selectors, and how to add a new governor type
- `examples/sample-output.md` — an annotated example of the text report

## Repository layout

```
QuorumReach/
├── SKILL.md              # This file
├── README.md             # Full documentation
├── foundry.toml          # Minimal config so cast can find the project root
├── LICENSE               # MIT
├── assets/
│   └── networks.json     # mainnet + testnet chain config
├── scripts/
│   └── forecast.sh       # The single bash script that does the work
├── references/
│   ├── forecasting-model.md
│   └── governors.md
├── examples/
│   └── sample-output.md
└── tests/
    └── test_forecast_smoke.sh   # Offline smoke test
```
