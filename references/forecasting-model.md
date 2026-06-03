# Forecasting Model

This file explains the math behind `src/forecaster.py`. The
implementation is intentionally simple — anything fancier needs
protocol-specific data (veToken decay, bribing markets, delegate
schedules) that we don't have generically.

## Inputs

For a given proposal the engine reads:

- `for`, `against`, `abstain` — current vote tallies.
- `quorum` — the quorum threshold in raw token units.
- `start_block` / `end_block` (on-chain) OR `start_ts` / `end_ts`
  (Snapshot) — voting window.
- `now` — current head block (on-chain) or unix timestamp (Snapshot).
- `history` — the last N closed proposals from the same governor
  (used only as a soft cap on the projection).

## Projection

Let `elapsed = (now - start) / (end - start)` ∈ [0, 1].

Case 1: `elapsed < 0.001` (proposal just started or history empty)

- If we have history, project to the **mean** of the historical
  final-tally totals.
- Otherwise, projection = current votes (the model has no signal).

Case 2: `elapsed >= 0.001`

- **Linear extrapolation**: `projected = current / elapsed`.
- If `projected > 1.5 * max(historical final)`, soft-cap the
  projection at `1.2 * max(historical final)` and add a note in the
  `explanation` field.

This is deliberately aggressive. Most DAOs exhibit *front-loaded*
voting (a few whales vote early), so a linear extrapolation usually
*overestimates* the final turnout. The model is calibrated to be
slightly pessimistic on early data and slightly optimistic on late
data — a fair trade for a single-number forecast.

## Label

The forecast label is a function of `ratio = projected / quorum`:

| Ratio range  | Label           | Confidence |
|--------------|-----------------|------------|
| 0.00 – 0.25  | `MISSED`        | 0.90       |
| 0.25 – 0.75  | `UNLIKELY`      | 0.70       |
| 0.75 – 1.00  | `REACH_QUORUM`  | 0.55       |
| 1.00 – 1.30  | `LIKELY`        | 0.75       |
| 1.30+        | `GUARANTEED`    | 0.90       |

The asymmetric confidence (lower in the 0.75–1.00 band) reflects the
fact that the closer to the threshold, the more a single whale can
tip the result either way.

## Why not a fancier model?

Three reasons:

1. **No intra-period data.** Without indexing `VoteCast` events
   we only see the current tally, not the curve that got us here.
2. **No supply / veToken data.** We can't normalize turnout to
   "share of supply" without a separate call to the governance
   token contract.
3. **Reliability over cleverness.** A linear model is auditable in
   30 seconds; a Gaussian process trained on a handful of proposals
   per DAO is not.

The engine is structured so that the projection step can be swapped
out (see `forecaster.py:forecast`) without touching the rest of the
codebase. A future version could add a Bayesian posterior over
historical curves if VoteCast event indexing is added.

## Limitations

- Cannot detect bribing markets, airdrop-driven turnout spikes, or
  sudden whale movements.
- Linear extrapolation underestimates the final value when a large
  portion of voters wait until the last 24h (a common pattern).
- History scan for OpenZeppelin governors is intentionally disabled
  (the ProposalCreated event topic hash varies across versions);
  pass `--lookback 0` or use a Compound governor for now if you
  need the soft cap.
