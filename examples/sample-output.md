# Example: Quorum Forecast Report

> Generated against a sample proposal on Pharos mainnet. See
> `SKILL.md` for the full command line.

```
================================================================
  QUORUM FORECAST — openzeppelin-governor  (0xGovernorOnPharos)
  Proposal id: 42
================================================================

  Current votes
    for:      1,800,000
    against:  50,000
    abstain:  10,000
    total:    1,860,000

  Quorum threshold:    4,000,000
  Elapsed:             50.0%
  Time remaining:      50
  Model:               linear

  >>> PROJECTED FINAL:  3,500,000  <<<
  >>> RATIO:            0.875            <<<
  >>> FORECAST:         REACH_QUORUM  (conf 0.55)  <<<

  Explanation: Linear extrapolation from 50.0% elapsed.

  History used:  6 past proposal(s)
```

## Reading the report

- **Forecast label** is one of `MISSED` / `UNLIKELY` /
  `REACH_QUORUM` / `LIKELY` / `GUARANTEED`.
- **Confidence** is calibrated per band (see
  `references/forecasting-model.md`). 0.55 in the `REACH_QUORUM`
  band means "we're close to the threshold, so a single whale
  could tip it either way."
- **Ratio** is `projected / quorum`. < 1 means forecast miss, > 1
  means forecast hit.
- **Model** is `linear` (extrapolation from elapsed fraction),
  `mean` (history mean when voting just started), or
  `no-data` (no signal at all).
- **Time remaining** is in blocks for on-chain governors, in
  seconds for Snapshot.

## Next steps for the user

1. **If `LIKELY` or `GUARANTEED`** — relax; the proposal should
   reach quorum.
2. **If `REACH_QUORUM`** — this is the close-call band. Watch
   whale wallets and bribing markets.
3. **If `UNLIKELY` or `MISSED`** — if you have votes left to cast,
   this is the time. If you're a delegate, ping your delegators.
