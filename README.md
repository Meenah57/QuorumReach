# QuorumReach — Quorum Forecaster

> Predict whether an on-chain or off-chain governance proposal will
> reach quorum before its voting deadline closes.

[![python](https://img.shields.io/badge/python-3.9%2B-blue)]()
[![license](https://img.shields.io/badge/license-MIT--0-green)]()
[![rpc](https://img.shields.io/badge/RPC-JSON--RPC%20%7C%20EVM-orange)]()

## Overview

QuorumReach reads live state from a governance contract (or a
Snapshot space) and projects the final vote tally at deadline using
a linear extrapolation seeded with the governor's own historical
turnout. The output is a single, audit-friendly forecast label
(`MISSED`, `UNLIKELY`, `REACH_QUORUM`, `LIKELY`, `GUARANTEED`) plus a
confidence score and a human-readable explanation.

It works for:

- **On-chain governors** — OpenZeppelin Governor and Compound Bravo.
- **Off-chain governors** — Snapshot (most DAOs that don't pay gas
  for voting).

## Features

- **On-chain forecast** — read proposal state, vote tallies, and
  quorum threshold via `eth_call`. No web3 framework dependency.
- **Snapshot support** — query the Snapshot Hub GraphQL API directly.
- **Five-tier label** — `MISSED` / `UNLIKELY` / `REACH_QUORUM` /
  `LIKELY` / `GUARANTEED` with calibrated confidence.
- **History-aware soft cap** — the projection is bounded by the
  governor's own historical maximum turnout to avoid runaway
  extrapolation.
- **Multi-format output** — text (default), JSON, Markdown, or HTML
  via the `report.py` formatter.
- **Agent-ready** — ships a `SKILL.md` at the repo root with the
  invocation contract an agent runtime needs to drive the tool.
- **Manual override** — supply `--quorum-absolute` when the governor
  doesn't expose a usable quorum read (Snapshot %-of-supply cases,
  custom DAOs).

## Supported networks

The tool runs against any EVM-compatible JSON-RPC endpoint for
on-chain governors, and against the Snapshot Hub for off-chain ones.
The following networks are explicitly supported out of the box and
used in the examples below.

| Network                 | Chain ID | RPC URL                              | Native token | Explorer                          |
|-------------------------|----------|--------------------------------------|--------------|-----------------------------------|
| Pharos Pacific Mainnet  | `1672`   | `https://rpc.pharos.xyz`             | PROS         | https://www.pharosscan.xyz/       |
| Pharos Atlantic Testnet | `688689` | `https://atlantic.dplabs-internal.com` | PHRS         | https://atlantic.pharosscan.xyz/  |

For off-chain governance, the Snapshot Hub is chain-agnostic:
`https://hub.snapshot.org/graphql`.

You can target either by passing the matching `--rpc-url` flag
(see [Usage](#usage)).

## Framework

- **Language:** Python 3.9+
- **RPC protocol:** JSON-RPC (`eth_call`, `eth_blockNumber`,
  `eth_getLogs`, `eth_chainId`)
- **Off-chain protocol:** GraphQL against the Snapshot Hub.
- **External CLIs (optional):** `cast` from
  [Foundry](https://book.getfoundry.xyz/) for manual cross-checks
  of proposal state; `jq` for ergonomic RPC URL extraction in shell
  pipelines.
- **No web3 framework required** — the engine speaks JSON-RPC
  directly over `requests` so it has the smallest possible install
  footprint.

## Dependencies

Runtime (Python):

- `requests>=2.31` — HTTP client used by `src/rpc.py` and the
  Snapshot GraphQL client.

External (only if you want the optional CLIs):

- `cast` / `forge` — Foundry CLI (https://book.getfoundry.xyz/getting-started/installation).
- `jq` — command-line JSON processor, used in README shell snippets.

Everything is pinned in `requirements.txt` at the repo root.

## Installation

```bash
# Clone
git clone https://github.com/Meenah57/QuorumReach.git
cd QuorumReach

# Install Python dependency
pip install -r requirements.txt

# (Optional) install Foundry if you want cast/forge fallback
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

No build step. No native compilation.

## Usage

### Forecast an on-chain proposal (Pharos mainnet)

```bash
python src/quorum_forecast.py \
  --governor 0xGovernorContractAddress \
  --proposal-id 42 \
  --rpc-url https://rpc.pharos.xyz
```

### Forecast an on-chain proposal (Pharos Atlantic testnet)

```bash
python src/quorum_forecast.py \
  --governor 0xGovernorContractAddress \
  --proposal-id 7 \
  --rpc-url https://atlantic.dplabs-internal.com
```

### Forecast a Snapshot proposal

```bash
python src/quorum_forecast.py \
  --governor aave.eth \
  --proposal-id 0xProposalIdHere \
  --mode snapshot
```

### Output as JSON, then format as Markdown

```bash
python src/quorum_forecast.py \
  --governor 0xGovernorContractAddress \
  --proposal-id 42 \
  --rpc-url https://rpc.pharos.xyz \
  --format json \
  | python src/report.py --format markdown --out forecast.md
```

### Output as HTML

```bash
python src/quorum_forecast.py \
  --governor 0xGovernorContractAddress \
  --proposal-id 42 \
  --rpc-url https://rpc.pharos.xyz \
  --format json \
  | python src/report.py --format html --out forecast.html
```

### Override the quorum threshold manually

```bash
python src/quorum_forecast.py \
  --governor 0xGovernorContractAddress \
  --proposal-id 42 \
  --rpc-url https://rpc.pharos.xyz \
  --quorum-absolute 4000000
```

### Command-line flags

| Flag                 | Required | Default | Description                                  |
|----------------------|----------|---------|----------------------------------------------|
| `--governor`         | yes      | —       | Governor address (0x…) or Snapshot space     |
| `--proposal-id`      | yes      | —       | Proposal id (string)                         |
| `--rpc-url`          | depends  | —       | JSON-RPC endpoint (required for on-chain)    |
| `--mode`             | no       | auto    | `auto`, `onchain`, or `snapshot`             |
| `--lookback`         | no       | 8       | How many past proposals to use as a soft cap |
| `--quorum-absolute`  | no       | —       | Override quorum threshold (raw token units)  |
| `--format`           | no       | text    | `text`, `json`, `markdown`, `html`           |
| `--out`              | no       | -       | Output file (`-` for stdout)                 |

### Sample output

See `examples/sample-output.md` for what a real forecast looks like.

## AI Agent Integration

This repository ships a `SKILL.md` at the root that any agent
runtime can load to discover the skill. The flow is:

1. The agent reads `SKILL.md` to learn the capability and required
   arguments (`--governor`, `--proposal-id`, optionally `--rpc-url`).
2. The agent determines the mode (on-chain vs Snapshot). If the
   user supplied a 0x address, the engine auto-detects on-chain.
3. The agent runs `python src/quorum_forecast.py` with the
   parameters and captures stdout (or `--out` to a file).
4. The agent surfaces the forecast label, confidence, ratio, and
   time-remaining as the top of its reply.
5. If a formatted report is needed, the agent pipes the JSON output
   through `python src/report.py --format <fmt>`.

A typical prompt that triggers the skill:

> "Will Pharos governance proposal #42 reach quorum? Governor is
> `0xGovernorContract`, RPC is `https://rpc.pharos.xyz`."

A typical reply:

> **Forecast: REACH_QUORUM** — confidence 0.55 — ratio 0.875 —
> projected 3,500,000 / quorum 4,000,000 — 50.0% elapsed, 50 blocks
> remaining. Linear extrapolation; close call.

## Repository layout

```
QuorumReach/
├── SKILL.md                       # Agent-facing skill spec
├── README.md                      # This file
├── LICENSE                        # MIT-0
├── requirements.txt
├── src/
│   ├── quorum_forecast.py         # CLI entry point
│   ├── governors.py               # On-chain + Snapshot interfaces
│   ├── forecaster.py              # Projection engine
│   ├── rpc.py                     # JSON-RPC client
│   └── report.py                  # Text / JSON / Markdown / HTML formatter
├── references/
│   ├── governors.md               # Supported governors + selectors
│   └── forecasting-model.md       # Math + scoring rules
└── examples/
    └── sample-output.md           # What a real forecast looks like
```

## How detection works

See `references/forecasting-model.md` for the math, label
thresholds, and confidence calibration. See
`references/governors.md` for the supported ABI selectors and how
to add a new governor.

## Roadmap

- [ ] Add a `--governor-type` flag to force Compound Bravo routing.
- [ ] Index `VoteCast` events to learn a per-DAO voting shape prior
  (replaces the current linear extrapolation).
- [ ] Bayesian posterior over historical curves for tighter
  confidence intervals.
- [ ] Auto-detect Pharos-native governance contracts when they ship.

## Contributing

PRs welcome — especially new governor implementations, additional
DEI strategy types for Snapshot, and benchmarks against real
proposals.

## License

[MIT-0](https://opensource.org/licenses/MIT-0) — free to use, modify,
redistribute. No attribution required.

---

**Author:** Meenah57
**Built with:** Python 3.9+, plain JSON-RPC, and a healthy distrust
of last-minute whale votes.
