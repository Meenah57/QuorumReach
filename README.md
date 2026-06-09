# QuorumReach — Quorum Forecaster

Predicts whether an on-chain or off-chain governance proposal will reach
quorum before its voting deadline closes. Works for **OpenZeppelin
Governor** and **Compound Bravo** contracts on any EVM chain, plus
**Snapshot** off-chain spaces.

The output is a single label (`MISSED` / `UNLIKELY` / `REACH_QUORUM` /
`LIKELY` / `GUARANTEED`) plus a confidence score and a one-line
explanation.

## Install

```bash
git clone https://github.com/Meenah57/QuorumReach
cd QuorumReach
```

That's the whole install. **No `pip install`, no `npm install`, no
`forge build`.** The skill uses only the Python standard library
(`urllib.request` for HTTP, `json`/`dataclasses` for everything else).
If you previously got `ModuleNotFoundError: No module named 'requests'`,
that bug is fixed — the skill used to depend on `requests` and no
longer does.

## Usage

### Forecast an on-chain proposal (any EVM RPC)

```bash
python3 src/quorum_forecast.py \
  --governor 0xGOVERNOR_ADDRESS \
  --proposal-id 42 \
  --rpc-url https://rpc.pharos.xyz
```

### Forecast a Snapshot (off-chain) proposal

```bash
python3 src/quorum_forecast.py \
  --governor aave.eth \
  --proposal-id 0xPROPOSAL_ID \
  --mode snapshot
```

### Output formats

```bash
# JSON, for an agent
python3 src/quorum_forecast.py --governor 0x... --proposal-id 42 \
  --rpc-url https://rpc.pharos.xyz --format json

# Markdown report, saved to a file
python3 src/quorum_forecast.py --governor 0x... --proposal-id 42 \
  --rpc-url https://rpc.pharos.xyz --format json \
  | python3 src/report.py --format markdown --out forecast.md
```

### Command-line flags

| Flag | Required | Default | What it does |
|---|---|---|---|
| `--governor` | yes | — | Governor address (0x…) or Snapshot space |
| `--proposal-id` | yes | — | Proposal id (string) |
| `--rpc-url` | for on-chain | — | JSON-RPC endpoint |
| `--mode` | no | auto | `auto`, `onchain`, or `snapshot` |
| `--lookback` | no | 8 | Past proposals used as a soft cap |
| `--quorum-absolute` | no | — | Override quorum threshold (raw token units) |
| `--format` | no | text | `text`, `json`, `markdown`, or `html` |
| `--out` | no | stdout | Output file (`-` for stdout) |

## Networks

| Network | Chain ID | RPC |
|---|---:|---|
| Pharos Pacific Mainnet | 1672 | `https://rpc.pharos.xyz` |
| Pharos Atlantic Testnet | 688689 | `https://atlantic.dplabs-internal.com` |

The skill works against **any EVM JSON-RPC endpoint** — just pass
`--rpc-url`. For off-chain, the Snapshot Hub is chain-agnostic
(`https://hub.snapshot.org/graphql`).

## How the math works

1. Read proposal state via `eth_call` (`proposalVotes`,
   `proposalDeadline`, `proposalSnapshot`, `quorum`, `votingPeriod`,
   `votingDelay`)
2. Compute time-elapsed / time-remaining ratio
3. Linear-extrapolate current votes to the deadline
4. Cap the projection at the governor's historical maximum turnout
5. Compare projection to quorum threshold
6. Map to a label: `MISSED` / `UNLIKELY` / `REACH_QUORUM` / `LIKELY` /
   `GUARANTEED`
7. Confidence score (0.0 - 1.0) from time-elapsed and historical
   volatility

Full math: `references/forecasting-model.md`. Full selector table:
`references/governors.md`.

## Use as a Python library (from inside an agent)

```python
import sys
sys.path.insert(0, "src")
from quorum_forecast import forecast

result = forecast(
    governor="0xGOVERNOR_ADDRESS",
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

**Zero.** Pure Python standard library — no `requests`, no `web3`, no
Foundry. Just `urllib.request`, `json`, and `dataclasses`.

## License

MIT-0 — free to use, modify, redistribute. No attribution required.
