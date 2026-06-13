# QuorumReach — Quorum Forecaster

> Predict whether a governance proposal will reach quorum before its voting deadline closes — on-chain (OZ Governor / Compound Bravo) or off-chain (Snapshot).

[![foundry](https://img.shields.io/badge/built%20with-Foundry-orange)]()
[![bash](https://img.shields.io/badge/script-bash-blue)]()
[![license](https://img.shields.io/badge/license-MIT-green)]()
[![pharos](https://img.shields.io/badge/network-Pharos-blueviolet)]()
[![ai-agent](https://img.shields.io/badge/callable%20by-AI%20agent-purple)]()

## What it is

This is a **skill built for the Pharos network** — a self-contained, deterministic bash script that runs on top of the [Pharos](https://pharos.network) EVM chains. It is **not** an AI agent itself, and not a chatbot. It is a single bash script that:

- takes input from the caller via CLI flags,
- reads live on-chain data from Pharos via `cast` (Foundry),
- runs its own scoring/heuristic logic in pure bash + `awk` + `jq`,
- prints a structured report (text or JSON) to stdout.

Reads the proposal's current vote tallies (for / against / abstain), quorum threshold, and the live block head via `cast`, computes the elapsed fraction of the voting period, and projects the final turnout with a linear extrapolation (or a history mean when voting just started). Emits a single label (`MISSED` / `UNLIKELY` / `REACH_QUORUM` / `LIKELY` / `GUARANTEED`) plus a confidence score and a one-line explanation. Three modes: `onchain` (default), `demo` (synthetic), and `snapshot` (stub — extend it).

## How it scores

Let `elapsed = (head - start) / (end - start)` ∈ [0, 1].

| Case | Projection |
|---|---|
| `elapsed < 0.001` (voting just started) | current votes (history mean is a stub in this version) |
| `elapsed >= 0.001` | **linear extrapolation**: `projected = current / elapsed` |

The label is a function of `ratio = projected / quorum`:

| Ratio range | Label | Confidence |
|---|---|---|
| 0.00 – 0.25 | `MISSED` | 0.90 |
| 0.25 – 0.75 | `UNLIKELY` | 0.70 |
| 0.75 – 1.00 | `REACH_QUORUM` | 0.55 |
| 1.00 – 1.30 | `LIKELY` | 0.75 |
| 1.30+ | `GUARANTEED` | 0.90 |

The asymmetric confidence (lower in the 0.75–1.00 band) reflects that the closer to the threshold, the more a single whale can tip the result either way. See `references/forecasting-model.md` for the full rationale.

## Use it from an AI agent

This skill is designed to be **called by an AI agent** (a Claude Code / Codex / Cursor agent, the Pharos Agent Center, or any custom LLM agent). The agent reads `SKILL.md` to discover the skill's flags, fills them in based on the user's request, and runs the bash script in its sandbox. The agent's job is just to translate "will proposal 42 reach quorum?" into `bash scripts/forecast.sh --mode onchain --governor 0x... --proposal-id 42`.

Typical agent-side flow:

```text
User -> Agent: "Will proposal 42 on this Governor reach quorum?"
Agent -> looks up SKILL.md for QuorumReach — Quorum Forecaster
Agent -> picks the right flag combo: --mode onchain --governor 0x... --proposal-id 42
Agent -> runs: bash scripts/forecast.sh --mode onchain --governor 0x... --proposal-id 42
Agent -> reads the verdict, presents the label + confidence to the user
```

The script prints structured output to stdout and human-readable progress to stderr, so the agent can parse the stdout cleanly (with `jq`) without being polluted by progress messages.

## Install

You need three things: **Foundry** (for `cast`), **jq** (for JSON pretty-printing), and **git** (to clone the repo).

```bash
# 1. Install Foundry (gives you cast, forge, anvil, chisel)
curl -L https://foundry.paradigm.xyz | bash
foundryup
# Reload your shell so the new commands are on PATH:
exec $SHELL
cast --version   # should print 1.x or higher

# 2. Install jq (required for --json output)
# macOS:   brew install jq
# Ubuntu:  sudo apt-get install -y jq
# Alpine:  apk add jq
jq --version

# 3. Clone this repo
git clone https://github.com/Meenah57/QuorumReach.git
cd QuorumReach
chmod +x scripts/*.sh tests/*.sh
```

## Quick test (30 seconds, no API keys needed)

```bash
bash scripts/forecast.sh --mode demo
```

The first time you run this, the script prints a synthetic forecast — no cast, no RPC, no setup needed.

## Usage

```bash
# Forecast a proposal on a real OZ Governor (mainnet)
bash scripts/forecast.sh --mode onchain \
  --governor 0xGOVERNOR_ADDRESS --proposal-id 42 --chain mainnet

# Demo mode (no cast or RPC needed)
bash scripts/forecast.sh --mode demo

# Output as JSON (for an agent)
bash scripts/forecast.sh --mode onchain --governor 0xADDR --proposal-id 42 --json

# Override the quorum threshold manually
bash scripts/forecast.sh --mode onchain --governor 0xADDR --proposal-id 42 \
  --quorum-absolute 4000000

# Testnet
bash scripts/forecast.sh --mode onchain --governor 0xADDR --proposal-id 42 --chain testnet
```

### All flags

```
--mode <onchain|demo|snapshot> --governor 0xADDR --proposal-id N --chain <mainnet|testnet> --lookback N --quorum-absolute N --json
```

| Flag | Description |
|---|---|
| `--mode <onchain \| demo \| snapshot>` | Forecasting mode (default: onchain) |
| `--governor 0xADDR` | On-chain governor contract address (required for onchain) |
| `--proposal-id N` | Proposal id as a non-negative integer (required for onchain) |
| `--chain mainnet \| testnet` | Pharos chain to read from (default: mainnet) |
| `--lookback N` | Number of past proposals to use for soft cap (default: 5; history mean is currently a stub) |
| `--quorum-absolute N` | Override the on-chain quorum (raw token units) |
| `--json` | Output as JSON (for agent consumption) |
| `-h`, `--help` | Show the help text |

## Supported governors

The onchain mode reads these selectors via `cast call`:

**OpenZeppelin Governor** (default):

| Function | Selector |
|---|---|
| `state(uint256)` | `0x3e4f49e6` |
| `proposalVotes(uint256)` | `0xda95691a` |
| `proposalSnapshot(uint256)` | `0x462aca47` |
| `proposalDeadline(uint256)` | `0x2e03ce1b` |
| `quorum(uint256)` | `0xf8ce5601` |

**Compound Bravo** (`GovernorAlpha` / `GovernorBravo`):

| Function | Selector |
|---|---|
| `proposals(uint256)` | `0x7d5d6a93` |
| `state(uint256)` | `0x3e4f49e6` |
| `quorumVotes()` | `0x973ab343` |

**Snapshot** (off-chain): stub in this version. Extend the script with a Snapshot Hub GraphQL query against `https://hub.snapshot.org/graphql`.

See `references/governors.md` for the full list and how to add a new governor type.

## Networks

The skill is built to run against the Pharos EVM chains. The chain config is stored in `assets/networks.json` and read at startup — no hardcoded URLs in the script.

| Network | Chain ID | RPC URL | Default |
|---|---:|---|:---:|
| mainnet (Pacific Ocean) | 1672 | `https://rpc.pharos.xyz` | ✓ |
| atlantic-testnet | 688689 | `https://atlantic.dplabs-internal.com` |  |

The script defaults to mainnet. Pass `--chain testnet` to use the testnet instead. You can also override the RPC URL by editing `assets/networks.json`.

## Set it up in an AI agent

Three install paths for any AI agent that wants to call this skill.

### Path A — Pharos Agent Center (for the official Pharos LLM agent)

The Pharos Agent Center is the official agent runtime for the Pharos network. It reads `SKILL.md` from any skill repo to discover capabilities, dependencies, and required flags.

1. **Copy the skill into the Agent Center's skills directory:**
   ```bash
   # After cloning this repo:
   cp -r scripts assets references examples SKILL.md README.md foundry.toml LICENSE \
     ~/.pharos/agent-center/skills/QuorumReach/
   ```

2. **Reload the Agent Center's skill registry:**
   ```bash
   pharos-agent reload-skills
   # or restart the Agent Center daemon
   ```

3. **Invoke from the agent's chat UI** (or via the Agent Center's CLI / API):
   ```text
   User: "Will proposal 42 on this Governor reach quorum before the vote closes?"
   Agent Center: loads QuorumReach — Quorum Forecaster, runs:
     bash ~/.pharos/agent-center/skills/QuorumReach/scripts/forecast.sh --mode onchain --governor 0xADDR --proposal-id N --chain mainnet
   ```

### Path B — `npx skills add` (for Claude Code, Cursor, Codex, generic MCP agents)

```bash
npx skills add https://github.com/Meenah57/QuorumReach --skill QuorumReach
```

The agent's `skills` plugin will discover the SKILL.md, surface the skill in its tool list, and let the LLM pick the right flags when the user asks.

### Path C — Manual copy (any agent that reads `~/.claude/skills/`)

```bash
mkdir -p ~/.claude/skills/QuorumReach
cp -r scripts assets references examples SKILL.md README.md foundry.toml LICENSE ~/.claude/skills/QuorumReach/
```

Restart the agent. It will pick up the new skill on next tool discovery.

### Path D — Direct invocation (shell agents, cron jobs, CI pipelines)

```bash
bash scripts/forecast.sh --mode demo
```

No agent needed — just shell + Foundry.

### What the agent says to invoke this skill

| Caller says | Script invocation |
|---|---|
| Forecast proposal `42` on OZ Governor `0xabc...` on Pharos mainnet | `bash scripts/forecast.sh --mode onchain --governor 0xabc... --proposal-id 42 --chain mainnet` |
| Run the quorum forecaster demo | `bash scripts/forecast.sh --mode demo` |
| Forecast and return JSON for an agent | `bash scripts/forecast.sh --mode onchain --governor 0xabc... --proposal-id 42 --json` |
| "Run the demo" | `bash scripts/forecast.sh --mode demo` |

The agent should read the script's `--help` output to discover all available flags, then build the right command line for the user's request.

## Security model

The skill is **read-only by design**:

- The script never imports, reads, or stores a private key.
- It reads governance state via `eth_call` (read-only RPC) — it cannot move funds or vote on proposals.
- It never submits a transaction, never writes to disk, never phones home.
- The only network call is to the user-configured RPC URL (or the Snapshot Hub GraphQL endpoint, if you extend the snapshot mode).

## Framework

| Layer | Tech | Purpose |
|---|---|---|
| Engine | **bash 4+** | Script host (single file per skill) |
| RPC client | **Foundry / cast** | All chain reads — `cast call` for state, proposalVotes, proposalSnapshot, proposalDeadline, quorum |
| Chain config | **JSON** (`assets/networks.json`) | Network endpoints + chain IDs |
| Data format | **JSON** | Cast's native output; `jq` used for pretty-printing and JSON building |
| Math | **awk** | Float division for elapsed fraction and ratio (bash only does integer) |
| Runtime | Any POSIX shell, Foundry 1.0+ | Tested on Linux + macOS |

## Dependencies

**Required:**
- [Foundry](https://getfoundry.sh) (gives you `cast`, `forge`, `anvil`)
- `bash` 4+ (preinstalled on macOS, Ubuntu 20+, most Linux)
- `awk` (preinstalled on every Unix)
- `jq` (for `--json` output)

**Optional:**
- `git` — only required if you're cloning the repo (you already have it)

## Tests

Each repo ships with a bash smoke test that verifies:
1. `--help` works (no cast required)
2. `--mode demo` produces a forecast
3. `--mode demo --json` is valid JSON
4. Unknown modes are rejected
5. `--mode onchain` requires `--governor` and `--proposal-id`
6. Bad addresses and bad proposal ids are rejected
7. Unknown flags and bad chains are rejected
8. The cast-missing error is clear (when cast is not installed)

```bash
bash tests/test_forecast_smoke.sh
```

The test runs offline by default. If cast is installed, you can extend it with a live test (the script hits `cast call` on the supplied governor address).

## Reference docs

The skill ships with two reference documents that explain the model and the supported governors in depth:

- `references/forecasting-model.md` — the math behind the label thresholds and the linear extrapolation
- `references/governors.md` — the supported OZ Governor / Compound Bravo / Snapshot interfaces, function selectors, and how to add a new governor type
- `examples/sample-output.md` — an annotated example of the text report

## Repository layout

```
QuorumReach/
├── SKILL.md              # Skill contract (Capability Index, Error Handling, Security Reminders)
├── README.md             # This file
├── foundry.toml          # Minimal config so cast can find the project root
├── LICENSE               # MIT
├── assets/
│   └── networks.json     # mainnet + testnet chain config (read by every script)
├── scripts/
│   └── forecast.sh          # The single bash script that does the work
├── references/
│   ├── forecasting-model.md
│   └── governors.md
├── examples/
│   └── sample-output.md
└── tests/
    └── test_forecast_smoke.sh   # Offline smoke test (no cast required)
```

## License

MIT — see `LICENSE`.
