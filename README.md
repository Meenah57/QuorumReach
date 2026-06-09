# QuorumReach — Quorum Forecaster

Predicts whether an on-chain or off-chain governance proposal will reach
quorum before its voting deadline closes. Built for AI agents that need a
quick yes/no on a governance call without writing five eth_call
themselves.

Output is a single label (`MISSED` / `UNLIKELY` / `REACH_QUORUM` /
`LIKELY` / `GUARANTEED`) plus a confidence score and a one-line
explanation.

Works for **on-chain governors** (OpenZeppelin Governor, Compound
Bravo) and **off-chain governors** (Snapshot).

## TL;DR for a total novice

You need two things: Python (already installed on Termux from your
earlier setup) and the code from this repo.

```bash
# 1. Get the code
git clone https://github.com/Meenah57/QuorumReach.git
cd QuorumReach

# 2. Try it (no args needed — runs a sample forecast)
python3 src/quorum_forecast.py --governor 0x4C70919472B8FE53924Fada6a562cD95089631B2 --proposal-id 42 --rpc-url https://rpc.pharos.xyz
```

That's it. No `pip install`, no `npm install`, no `forge build`, no
environment setup. The skill uses **only the Python standard library**.

If you see a forecast line like `Forecast: REACH_QUORUM — confidence
0.55 — ...`, the skill is working.

## Install

```bash
git clone https://github.com/Meenah57/QuorumReach.git
cd QuorumReach
```

**That's the whole install.** No dependencies, no build step. Just
Python 3.9+ (which Termux already gives you) and this repo.

If you previously saw `ModuleNotFoundError: No module named 'requests'`,
that was a bug — the skill used to need the `requests` library, but
it now uses Python's built-in `urllib.request` instead. So no `pip
install` step is needed, ever.

## How a beginner uses it — full walkthrough

### Scenario: "I just want to see it work"

```bash
# 1. Get the code
git clone https://github.com/Meenah57/QuorumReach.git
cd QuorumReach

# 2. Run a forecast
python3 src/quorum_forecast.py \
  --governor 0x4C70919472B8FE53924Fada6a562cD95089631B2 \
  --proposal-id 42 \
  --rpc-url https://rpc.pharos.xyz
```

The output will look like:

```
Forecast: REACH_QUORUM — confidence 0.55 — ratio 0.875
  projected 3,500,000 / quorum 4,000,000
  50.0% elapsed, 50 blocks remaining
  Linear extrapolation; close call.
```

### Scenario: "Forecast a Snapshot (off-chain) proposal"

```bash
python3 src/quorum_forecast.py \
  --governor aave.eth \
  --proposal-id 0xProposalIdHere \
  --mode snapshot
```

### Scenario: "Get the result as JSON for my agent"

```bash
python3 src/quorum_forecast.py \
  --governor 0x4C70919472B8FE53924Fada6a562cD95089631B2 \
  --proposal-id 42 \
  --rpc-url https://rpc.pharos.xyz \
  --format json
```

### Scenario: "Get a Markdown report"

```bash
python3 src/quorum_forecast.py \
  --governor 0x4C70919472B8FE53924Fada6a562cD95089631B2 \
  --proposal-id 42 \
  --rpc-url https://rpc.pharos.xyz \
  --format json \
  | python3 src/report.py --format markdown --out forecast.md

cat forecast.md
```

## All command-line flags

| Flag | Required | Default | What it does |
|---|---|---|---|
| `--governor` | yes | — | Governor address (0x…) or Snapshot space (aave.eth) |
| `--proposal-id` | yes | — | Proposal id (any string) |
| `--rpc-url` | for on-chain | — | JSON-RPC endpoint (e.g. `https://rpc.pharos.xyz`) |
| `--mode` | no | auto | `auto`, `onchain`, or `snapshot` |
| `--lookback` | no | 8 | How many past proposals to use as a soft cap |
| `--quorum-absolute` | no | — | Override quorum threshold (raw token units) |
| `--format` | no | text | `text`, `json`, `markdown`, or `html` |
| `--out` | no | stdout | Output file (`-` for stdout) |

## Supported networks

| Network | Chain ID | RPC |
|---|---:|---|
| Pharos Pacific Mainnet | 1672 | `https://rpc.pharos.xyz` |
| Pharos Atlantic Testnet | 688689 | `https://atlantic.dplabs-internal.com` |

The skill works against **any EVM JSON-RPC endpoint** — just pass
`--rpc-url`. For off-chain, the Snapshot Hub is chain-agnostic
(`https://hub.snapshot.org/graphql`).

## How the math works

1. Read proposal state via `eth_call` (proposalVotes, proposalDeadline,
   proposalSnapshot, quorum, votingPeriod, votingDelay)
2. Compute time-elapsed / time-remaining ratio
3. Linear-extrapolate current votes to the deadline
4. Cap the projection at the governor's historical maximum turnout
5. Compare projection to quorum threshold
6. Map to a label: `MISSED` / `UNLIKELY` / `REACH_QUORUM` / `LIKELY` /
   `GUARANTEED`
7. Assign a confidence score (0.0 - 1.0) based on time-elapsed and
   historical volatility

Full math: `references/forecasting-model.md`. Full selector table:
`references/governors.md`.

## Use as a Python library (from inside an agent)

```python
import sys
sys.path.insert(0, "src")
from quorum_forecast import forecast

result = forecast(
    governor="0x4C70919472B8FE53924Fada6a562cD95089631B2",
    proposal_id="42",
    rpc_url="https://rpc.pharos.xyz",
)
print(result.label, result.confidence, result.explanation)
```

## AI Agent Integration

This repo ships a `SKILL.md` at the root that any agent runtime can
load to discover the skill. A typical flow:

1. Agent reads `SKILL.md` to learn the capability and required args
2. Agent determines the mode (on-chain vs Snapshot)
3. Agent runs `python3 src/quorum_forecast.py` and captures stdout
4. Agent surfaces the forecast label + confidence as the top of its
   reply

A typical prompt:

> "Will Pharos governance proposal #42 reach quorum? Governor is
> `0x4C70919472B8FE53924Fada6a562cD95089631B2`, RPC is
> `https://rpc.pharos.xyz`."

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
├── src/
│   ├── quorum_forecast.py         # CLI entry point
│   ├── governors.py               # On-chain + Snapshot interfaces
│   ├── forecaster.py              # Projection engine
│   ├── rpc.py                     # JSON-RPC client (stdlib only)
│   └── report.py                  # Text / JSON / Markdown / HTML formatter
├── references/
│   ├── governors.md               # Supported governors + selectors
│   └── forecasting-model.md       # Math + scoring rules
└── examples/
    └── sample-output.md           # What a real forecast looks like
```

## Dependencies

**Zero.** Pure Python standard library — no `pip install`, no
`requests`, no `web3`, no Foundry. Just `urllib.request`, `json`, and
`dataclasses` from the standard library.

(An earlier version of this repo needed `requests`; that's been
removed. If you previously got `ModuleNotFoundError: No module named
'requests'`, just `git pull` — the bug is fixed.)

## License

MIT-0 — free to use, modify, redistribute. No attribution required.
