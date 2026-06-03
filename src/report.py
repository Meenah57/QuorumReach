"""
report.py - Format a quorum forecast for human or agent consumption.

Input: a JSON object with the following top-level keys:
  - proposal: dict mirroring ProposalState fields
  - forecast: dict mirroring Forecast fields
  - governor: { name, address/space, chain_id }
  - history_used: int (how many historical proposals informed the forecast)
"""
from __future__ import annotations
import argparse
import json
import sys
from typing import Any, Dict


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _label_color(label: str) -> str:
    return {
        "GUARANTEED":   "\033[32m",  # green
        "LIKELY":       "\033[32m",
        "REACH_QUORUM": "\033[33m",  # yellow
        "UNLIKELY":     "\033[33m",
        "MISSED":       "\033[31m",  # red
        "UNKNOWN":      "\033[90m",
    }.get(label, "")


RESET = "\033[0m"


def render_text(r: Dict[str, Any], use_color: bool = True) -> str:
    p = r["proposal"]
    f = r["forecast"]
    g = r["governor"]
    color = _label_color(f["label"]) if use_color else ""
    lines = []
    lines.append("=" * 64)
    lines.append(f"  QUORUM FORECAST — {g.get('name','')}  ({g.get('address_or_space','')})")
    lines.append(f"  Proposal id: {p['proposal_id']}")
    lines.append("=" * 64)
    lines.append("")
    lines.append(f"  Current votes")
    lines.append(f"    for:      {_fmt_int(p['for_votes'])}")
    lines.append(f"    against:  {_fmt_int(p['against_votes'])}")
    lines.append(f"    abstain:  {_fmt_int(p['abstain_votes'])}")
    lines.append(f"    total:    {_fmt_int(f['current_total'])}")
    lines.append("")
    lines.append(f"  Quorum threshold:    {_fmt_int(f['quorum'])}")
    lines.append(f"  Elapsed:             {_fmt_pct(f['elapsed_fraction'])}")
    lines.append(f"  Time remaining:      {f['time_remaining']:,}")
    lines.append(f"  Model:               {f['model']}")
    lines.append("")
    lines.append(f"  >>> PROJECTED FINAL:  {_fmt_int(f['projected_total'])}  <<<")
    lines.append(f"  >>> RATIO:            {f['ratio']:.3f}            <<<")
    lines.append(f"  >>> FORECAST:         {color}{f['label']}{RESET}  (conf {f['confidence']:.2f})  <<<")
    lines.append("")
    lines.append(f"  Explanation: {f['explanation']}")
    lines.append("")
    lines.append(f"  History used:  {r.get('history_used', 0)} past proposal(s)")
    return "\n".join(lines) + "\n"


def render_markdown(r: Dict[str, Any]) -> str:
    p = r["proposal"]
    f = r["forecast"]
    g = r["governor"]
    lines = []
    lines.append(f"# Quorum Forecast — `{g.get('name','')}`")
    lines.append("")
    lines.append(f"- **Proposal id:** `{p['proposal_id']}`")
    lines.append(f"- **Governor / space:** `{g.get('address_or_space','')}`")
    lines.append(f"- **Chain id:** {g.get('chain_id','-')}")
    lines.append("")
    lines.append("## Current tally")
    lines.append("")
    lines.append("| Choice   | Votes |")
    lines.append("|----------|-------|")
    lines.append(f"| For      | {_fmt_int(p['for_votes'])} |")
    lines.append(f"| Against  | {_fmt_int(p['against_votes'])} |")
    lines.append(f"| Abstain  | {_fmt_int(p['abstain_votes'])} |")
    lines.append(f"| **Total**| **{_fmt_int(f['current_total'])}** |")
    lines.append("")
    lines.append("## Forecast")
    lines.append("")
    lines.append(f"### 🎯 **{f['label']}** (confidence {f['confidence']:.2f})")
    lines.append("")
    lines.append(f"- **Projected final votes:** {_fmt_int(f['projected_total'])}")
    lines.append(f"- **Quorum threshold:**     {_fmt_int(f['quorum'])}")
    lines.append(f"- **Ratio (projected / quorum):** {f['ratio']:.3f}")
    lines.append(f"- **Elapsed:** { _fmt_pct(f['elapsed_fraction']) }")
    lines.append(f"- **Time remaining:** {f['time_remaining']:,}")
    lines.append(f"- **Model used:** `{f['model']}`")
    lines.append("")
    lines.append(f"> {f['explanation']}")
    return "\n".join(lines) + "\n"


def render_html(r: Dict[str, Any]) -> str:
    p = r["proposal"]
    f = r["forecast"]
    g = r["governor"]
    label_color = {
        "GUARANTEED": "#1e8e3e",
        "LIKELY":     "#1e8e3e",
        "REACH_QUORUM":"#d93025",
        "UNLIKELY":   "#d93025",
        "MISSED":     "#a50e0e",
        "UNKNOWN":    "#5f6368",
    }.get(f["label"], "#202124")
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>Quorum Forecast — {p['proposal_id']}</title>
<style>
  body {{ font: 14px/1.4 system-ui, sans-serif; max-width: 800px; margin: 32px auto; padding: 0 16px; color: #202124; }}
  h1 {{ border-bottom: 2px solid #202124; padding-bottom: 4px; }}
  .label {{ font-size: 32px; font-weight: 800; color: {label_color}; margin: 16px 0 4px; }}
  .ratio {{ font-size: 18px; color: #5f6368; margin-bottom: 16px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
  th, td {{ border: 1px solid #dadce0; padding: 6px 8px; text-align: left; font-size: 13px; }}
  th {{ background: #f8f9fa; }}
  code {{ background: #f1f3f4; padding: 1px 4px; border-radius: 3px; }}
  .explain {{ background: #f8f9fa; border-left: 3px solid #1a73e8; padding: 8px 12px; margin-top: 16px; font-size: 13px; }}
</style></head><body>
<h1>Quorum Forecast</h1>
<p><strong>Governor / space:</strong> <code>{g.get('address_or_space','')}</code><br>
<strong>Proposal id:</strong> <code>{p['proposal_id']}</code><br>
<strong>Chain id:</strong> {g.get('chain_id','-')}</p>

<p class="label">{f['label']}</p>
<p class="ratio">confidence {f['confidence']:.2f} &middot; ratio {f['ratio']:.3f} &middot; projected {_fmt_int(f['projected_total'])} / quorum {_fmt_int(f['quorum'])}</p>

<h2>Current tally</h2>
<table>
<thead><tr><th>Choice</th><th>Votes</th></tr></thead>
<tbody>
<tr><td>For</td><td>{_fmt_int(p['for_votes'])}</td></tr>
<tr><td>Against</td><td>{_fmt_int(p['against_votes'])}</td></tr>
<tr><td>Abstain</td><td>{_fmt_int(p['abstain_votes'])}</td></tr>
<tr><td><strong>Total</strong></td><td><strong>{_fmt_int(f['current_total'])}</strong></td></tr>
</tbody>
</table>

<p>Elapsed: {_fmt_pct(f['elapsed_fraction'])} &middot; time remaining: {f['time_remaining']:,} &middot; model: <code>{f['model']}</code></p>

<p class="explain">{f['explanation']}</p>
</body></html>
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="input", default="-")
    p.add_argument("--format", choices=["text", "markdown", "html", "json"], default="text")
    p.add_argument("--out", default="-")
    p.add_argument("--no-color", action="store_true")
    args = p.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input).read()
    r = json.loads(raw)

    if args.format == "json":
        out = json.dumps(r, indent=2)
    elif args.format == "markdown":
        out = render_markdown(r)
    elif args.format == "html":
        out = render_html(r)
    else:
        out = render_text(r, use_color=not args.no_color)

    if args.out == "-":
        sys.stdout.write(out)
    else:
        with open(args.out, "w") as f:
            f.write(out)


if __name__ == "__main__":
    main()
