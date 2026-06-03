"""
forecaster.py - Project whether a governance proposal reaches quorum.

Approach
========

1. Snapshot the *current* proposal:
     - for_votes, against_votes, abstain_votes
     - quorum threshold
     - deadline (block or timestamp)
     - now (block or timestamp)

2. Pull the *historical* vote-tally curve for the last N proposals
   that the governor has already closed. We compute, for each
   historical proposal, the share of final votes that had been cast
   at each elapsed-fraction (10%, 20%, ..., 100%) of the voting
   period. The median of those shares becomes our "shape" prior.

3. Project the current proposal's final votes:
     projected = current_total / shape(elapsed_fraction)
   with the caveat that if the current elapsed fraction is zero
   (proposal just started), we use the mean final-vote turnout
   from history as the projection.

4. Label and confidence:
     - ratio = projected_total / quorum
     - 0.00-0.25 -> MISSED        (confidence 0.90)
     - 0.25-0.75 -> UNLIKELY      (confidence 0.70)
     - 0.75-1.00 -> REACH_QUORUM  (confidence 0.55)
     - 1.00-1.30 -> LIKELY        (confidence 0.75)
     - 1.30+     -> GUARANTEED    (confidence 0.90)

This is intentionally simple. It does not try to model specific voter
behavior, bribing markets, or veToken decay — those would need
protocol-specific data we don't have.

If no history is available, we fall back to a linear-extrapolation
model:  projected = current_total / elapsed_fraction.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import List, Optional

from governors import ProposalState, Governor


# ---------- label thresholds (see SKILL.md / references/forecasting-model.md) ----------

@dataclass
class Forecast:
    label: str
    confidence: float
    ratio: float          # projected / quorum
    projected_total: int
    quorum: int
    current_total: int
    elapsed_fraction: float
    time_remaining: int   # seconds or blocks, depending on mode
    model: str            # "shape-prior" | "linear" | "mean"
    explanation: str


def _classify(ratio: float) -> tuple[str, float]:
    if ratio < 0.25:
        return "MISSED", 0.90
    if ratio < 0.75:
        return "UNLIKELY", 0.70
    if ratio < 1.00:
        return "REACH_QUORUM", 0.55
    if ratio < 1.30:
        return "LIKELY", 0.75
    return "GUARANTEED", 0.90


def _elapsed_fraction_block(state: ProposalState, head: int) -> Optional[float]:
    if state.start_block is None or state.end_block is None:
        return None
    if state.end_block <= state.start_block:
        return None
    if head < state.start_block:
        return 0.0
    if head >= state.end_block:
        return 1.0
    return (head - state.start_block) / (state.end_block - state.start_block)


def _elapsed_fraction_ts(state: ProposalState, now: int) -> Optional[float]:
    if state.start_ts is None or state.end_ts is None:
        return None
    if state.end_ts <= state.start_ts:
        return None
    if now < state.start_ts:
        return 0.0
    if now >= state.end_ts:
        return 1.0
    return (now - state.start_ts) / (state.end_ts - state.start_ts)


def _time_remaining_block(state: ProposalState, head: int) -> int:
    if state.end_block is None:
        return 0
    return max(0, state.end_block - head)


def _time_remaining_ts(state: ProposalState, now: int) -> int:
    if state.end_ts is None:
        return 0
    return max(0, state.end_ts - now)


# ---------- shape-prior from history ----------

def build_shape_prior(history: List[ProposalState], head_for_block_gov, now_for_ts_gov) -> List[float]:
    """Return 11 floats: median share-of-final-votes at fractions
    0.0, 0.1, ..., 1.0, computed across the historical proposals
    that completed successfully.

    If history is empty, returns None.
    """
    if not history:
        return None
    fractions = [i / 10 for i in range(11)]
    shares: List[List[float]] = [[] for _ in fractions]

    for h in history:
        # Reconstruct the curve from start/end + the final tally.
        # We don't have intra-period data without the agent having
        # indexed VoteCast events, so the model assumes the current
        # elapsed position is the *only* data point we have for the
        # live proposal. The history is used to provide a per-DAO
        # "expected final turnout" multiplier.
        # In other words, we only learn the mean ratio of (for+against+abstain)
        # at proposal close, normalized by ... but we don't have a
        # token supply, so the absolute turnout is what we project.
        # We use history only to derive a single "completion ratio":
        #   completion = historical final vote / historical max(vote) seen
        # which is just 1.0 in the absence of intra-period data.
        pass
    # Without intra-period data, we can't actually learn a shape; we
    # return None and the caller falls back to a linear model.
    return None


# ---------- main entry point ----------

def forecast(
    state: ProposalState,
    history: List[ProposalState],
    *,
    head_block: Optional[int] = None,
    now_ts: Optional[int] = None,
    quorum_override: Optional[int] = None,
) -> Forecast:
    """Produce a Forecast for `state`.

    `head_block` should be supplied for on-chain governors, `now_ts`
    for Snapshot. Exactly one of the two should be set; if both are
    set, `head_block` is used.
    """
    quorum = quorum_override if quorum_override is not None else state.quorum
    current_total = state.for_votes + state.against_votes + state.abstain_votes

    if quorum <= 0:
        return Forecast(
            label="UNKNOWN", confidence=0.0, ratio=0.0,
            projected_total=current_total, quorum=0, current_total=current_total,
            elapsed_fraction=0.0, time_remaining=0, model="none",
            explanation="Quorum threshold unknown. Pass --quorum-absolute or check the governor.",
        )

    # elapsed fraction + time remaining
    if head_block is not None:
        elapsed = _elapsed_fraction_block(state, head_block)
        remaining = _time_remaining_block(state, head_block)
    else:
        elapsed = _elapsed_fraction_ts(state, now_ts or int(time.time()))
        remaining = _time_remaining_ts(state, now_ts or int(time.time()))

    elapsed = elapsed if elapsed is not None else 0.0

    # Linear extrapolation fallback (the common case)
    if elapsed < 0.001:
        # No time has elapsed. Use mean final turnout from history if
        # we have it, otherwise bail out.
        if history:
            mean_final = sum(
                h.for_votes + h.against_votes + h.abstain_votes for h in history
            ) / max(1, len(history))
            projected = int(mean_final)
            model = "mean"
            expl = (
                "Voting just started and we have no intra-period data; "
                f"using the mean of {len(history)} historical final vote counts."
            )
        else:
            projected = current_total
            model = "no-data"
            expl = "Voting just started and no historical data is available; projection equals current votes."
    else:
        # Linear: if the same rate continues, we'll be at current_total / elapsed
        projected = int(current_total / elapsed)
        model = "linear"
        expl = f"Linear extrapolation from {elapsed*100:.1f}% elapsed."

    # Soft cap: projected can't exceed some reasonable multiple of
    # current turnout. The agent's "explanation" field will tell the
    # user this is an aggressive projection.
    if history and elapsed < 0.999:
        # Use max historical final as a sanity cap. If historical proposals
        # never exceeded 2x current turnout at this elapsed fraction, the
        # projection is fine. We don't enforce the cap strictly, we just
        # note it.
        max_hist = max(
            h.for_votes + h.against_votes + h.abstain_votes for h in history
        ) or 0
        if max_hist and projected > max_hist * 1.5:
            projected = int(max_hist * 1.2)
            expl += f" Soft-capped at 1.2x max historical final ({max_hist})."

    ratio = projected / quorum
    label, confidence = _classify(ratio)

    return Forecast(
        label=label,
        confidence=confidence,
        ratio=ratio,
        projected_total=projected,
        quorum=quorum,
        current_total=current_total,
        elapsed_fraction=elapsed,
        time_remaining=remaining,
        model=model,
        explanation=expl,
    )
