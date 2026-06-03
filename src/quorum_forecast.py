"""
quorum_forecast.py - CLI entry point.

Usage:
  python quorum_forecast.py --governor 0xAddr --proposal-id 42
                            --rpc-url https://rpc.pharos.xyz
                            [--lookback 8] [--format json]
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from typing import Any, Dict

from rpc import RpcClient
from governors import (
    detect_mode,
    make_governor,
    ProposalState,
    OZGovernor,
    CompoundBravoGovernor,
    SnapshotGovernor,
)
from forecaster import forecast, Forecast


def _format_eta(remaining: int, is_block: bool) -> str:
    if is_block:
        return f"{remaining:,} blocks"
    secs = remaining
    if secs <= 0:
        return "0s"
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def run(args: argparse.Namespace) -> Dict[str, Any]:
    mode = args.mode
    if mode == "auto":
        mode = detect_mode(args.governor)

    rpc: RpcClient = None  # type: ignore
    if mode == "onchain":
        if not args.rpc_url:
            raise SystemExit("error: --rpc-url is required for on-chain mode")
        rpc = RpcClient(args.rpc_url)

    governor = make_governor(mode, args.governor, rpc)

    # Live state
    state: ProposalState = governor.current_state(args.proposal_id)

    # Historical states (best-effort, may be empty)
    history: list[ProposalState] = []
    try:
        history = governor.historical_states(args.lookback)
    except Exception as e:  # noqa: BLE001
        print(f"[!] history scan failed: {e}", file=sys.stderr)

    # Head / now
    head_block = rpc.block_number() if rpc else None
    now_ts = int(time.time())

    fc: Forecast = forecast(
        state,
        history,
        head_block=head_block,
        now_ts=now_ts,
        quorum_override=args.quorum_absolute,
    )

    is_block = mode == "onchain"
    payload = {
        "governor": {
            "name": governor.name,
            "address_or_space": args.governor,
            "chain_id": state.chain_id,
            "mode": mode,
        },
        "proposal": {
            "proposal_id": state.proposal_id,
            "for_votes":   state.for_votes,
            "against_votes": state.against_votes,
            "abstain_votes": state.abstain_votes,
            "quorum":      state.quorum,
            "start_block": state.start_block,
            "end_block":   state.end_block,
            "start_ts":    state.start_ts,
            "end_ts":      state.end_ts,
            "state_int":   state.state,
            "proposer":    state.proposer,
        },
        "forecast": {
            "label":            fc.label,
            "confidence":       fc.confidence,
            "ratio":            fc.ratio,
            "projected_total":  fc.projected_total,
            "quorum":           fc.quorum,
            "current_total":    fc.current_total,
            "elapsed_fraction": fc.elapsed_fraction,
            "time_remaining":   fc.time_remaining,
            "time_remaining_human": _format_eta(fc.time_remaining, is_block),
            "model":            fc.model,
            "explanation":      fc.explanation,
        },
        "history_used": len(history),
    }
    return payload


def main():
    p = argparse.ArgumentParser(
        description="Forecast whether a governance proposal will reach quorum."
    )
    p.add_argument("--governor", required=True,
                   help="Governor contract address (0x…) or Snapshot space (e.g. aave.eth)")
    p.add_argument("--proposal-id", required=True,
                   help="Proposal id (uint256 as string for on-chain, or Snapshot id)")
    p.add_argument("--rpc-url", default=None,
                   help="JSON-RPC endpoint (required for on-chain mode)")
    p.add_argument("--mode", choices=["auto", "onchain", "snapshot"], default="auto")
    p.add_argument("--lookback", type=int, default=8,
                   help="How many past proposals to use as shape prior (default 8)")
    p.add_argument("--quorum-absolute", type=int, default=None,
                   help="Override quorum threshold (raw token units)")
    p.add_argument("--format", choices=["text", "json", "markdown", "html"], default="text")
    p.add_argument("--out", default="-")
    args = p.parse_args()

    payload = run(args)

    if args.format == "json":
        out = json.dumps(payload, indent=2)
    elif args.format == "markdown":
        from report import render_markdown
        out = render_markdown(payload)
    elif args.format == "html":
        from report import render_html
        out = render_html(payload)
    else:
        from report import render_text
        out = render_text(payload, use_color=sys.stdout.isatty())

    if args.out == "-":
        sys.stdout.write(out)
    else:
        with open(args.out, "w") as f:
            f.write(out)


if __name__ == "__main__":
    main()
