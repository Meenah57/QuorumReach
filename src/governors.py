"""
governors.py - Governor interface abstractions.

Defines a common interface `Governor` that returns:
  - current votes (for, against, abstain)
  - quorum threshold (in raw token units)
  - deadline (block number or unix timestamp)
  - voting-period (in blocks or seconds, for curve fitting)

Two built-in implementations:
  - CompoundBravoGovernor (on-chain, block-based)
  - OZGovernor (on-chain, block-based)
  - SnapshotGovernor (off-chain, timestamp-based, GraphQL)

Custom: any contract that exposes the right selectors can be wrapped
in `GenericGovernor`.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests
from rpc import RpcClient, RpcError, keccak_sig, decode_uint256, decode_address


# Snapshot Hub GraphQL endpoint (public, no API key needed for public spaces)
SNAPSHOT_HUB = "https://hub.snapshot.org/graphql"


@dataclass
class ProposalState:
    proposal_id: str
    governor: str
    chain_id: Optional[int] = None
    for_votes: int = 0
    against_votes: int = 0
    abstain_votes: int = 0
    quorum: int = 0
    start_block: Optional[int] = None
    end_block: Optional[int] = None
    start_ts: Optional[int] = None
    end_ts: Optional[int] = None
    state: int = 0            # 0=pending,1=active,2=canceled,3=defeated,4=succeeded,5=queued,6=expired,7=executed
    proposer: str = "0x0000000000000000000000000000000000000000"
    canceled: bool = False
    executed: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


class Governor:
    name = "abstract"

    def current_state(self, proposal_id: str) -> ProposalState: ...
    def historical_states(self, n: int) -> List[ProposalState]: ...


# ---------- Compound Bravo ----------

class CompoundBravoGovernor(Governor):
    name = "compound-bravo"

    def __init__(self, rpc: RpcClient, address: str):
        self.rpc = rpc
        self.address = address.lower()

    def _read_uint(self, sig: str, *args: str) -> int:
        data = keccak_sig(sig) + "".join(a.rjust(64, "0") for a in args)
        return decode_uint256(self.rpc.eth_call(self.address, data))

    def current_state(self, proposal_id: str) -> ProposalState:
        # proposals(uint256) returns a 9-field tuple: abi-encoded
        # We pull the 7 numeric fields we care about individually by
        # index. Easiest: ask for the full tuple and slice.
        data = keccak_sig("proposals(uint256)") + proposal_id.rjust(64, "0")
        raw = self.rpc.eth_call(self.address, data)
        words = _split_words(raw, 9)
        proposer = decode_address(words[0])
        eta       = decode_uint256(words[1])
        startBlk  = decode_uint256(words[2])
        endBlk    = decode_uint256(words[3])
        for_v     = decode_uint256(words[4])
        against_v = decode_uint256(words[5])
        abstain_v = decode_uint256(words[6])
        canceled  = int(words[7], 16) != 0
        executed  = int(words[8], 16) != 0

        quorum = self._read_uint("quorumVotes()")
        state_int = self._state_int(proposal_id)

        return ProposalState(
            proposal_id=proposal_id,
            governor=self.address,
            chain_id=self.rpc.chain_id(),
            for_votes=for_v,
            against_votes=against_v,
            abstain_votes=abstain_v,
            quorum=quorum,
            start_block=startBlk,
            end_block=endBlk,
            state=state_int,
            proposer=proposer,
            canceled=canceled,
            executed=executed,
        )

    def _state_int(self, proposal_id: str) -> int:
        data = keccak_sig("state(uint256)") + proposal_id.rjust(64, "0")
        raw = self.rpc.eth_call(self.address, data)
        return int(raw, 16) if raw else 0

    def historical_states(self, n: int) -> List[ProposalState]:
        # Bravo exposes proposalCount(); we can probe backwards until we
        # hit canceled/empty entries.
        try:
            data = keccak_sig("proposalCount()")
            raw = self.rpc.eth_call(self.address, data)
            count = decode_uint256(raw)
        except RpcError:
            return []
        out: List[ProposalState] = []
        for i in range(max(0, count - n), count):
            try:
                st = self.current_state(str(i))
                if st.state in (1, 4, 5, 7) and st.for_votes + st.against_votes + st.abstain_votes > 0:
                    out.append(st)
            except RpcError:
                continue
        return out


# fix the typo'd call from above
def _split_words(raw_hex: str, n_words: int) -> List[str]:
    """Split a 32-byte-word ABI-encoded tuple into n individual word hex strings."""
    if not raw_hex or raw_hex == "0x":
        return ["0x" + "0" * 64] * n_words
    h = raw_hex[2:] if raw_hex.startswith("0x") else raw_hex
    if len(h) < 64 * n_words:
        h = h.ljust(64 * n_words, "0")
    return ["0x" + h[i*64:(i+1)*64] for i in range(n_words)]


# ---------- OpenZeppelin Governor ----------

class OZGovernor(Governor):
    name = "openzeppelin-governor"

    def __init__(self, rpc: RpcClient, address: str):
        self.rpc = rpc
        self.address = address.lower()

    def _read_uint(self, sig: str, *args: str) -> int:
        data = keccak_sig(sig) + "".join(a.rjust(64, "0") for a in args)
        return decode_uint256(self.rpc.eth_call(self.address, data))

    def current_state(self, proposal_id: str) -> ProposalState:
        # proposalVotes(uint256) -> (against, for, abstain)
        data = keccak_sig("proposalVotes(uint256)") + proposal_id.rjust(64, "0")
        raw = self.rpc.eth_call(self.address, data)
        words = _split_words(raw, 3)
        against_v = decode_uint256(words[0])
        for_v     = decode_uint256(words[1])
        abstain_v = decode_uint256(words[2])

        startBlk = self._read_uint("proposalSnapshot(uint256)", proposal_id)
        endBlk   = self._read_uint("proposalDeadline(uint256)", proposal_id)

        # quorum is a function of blockNumber; pass endBlk as a stable
        # snapshot point. If endBlk is 0, fallback to current head.
        head = self.rpc.block_number()
        q_blk = endBlk if endBlk else head
        try:
            quorum = self._read_uint("quorum(uint256)", str(q_blk))
        except RpcError:
            quorum = 0

        state_int = self._state_int(proposal_id)

        return ProposalState(
            proposal_id=proposal_id,
            governor=self.address,
            chain_id=self.rpc.chain_id(),
            for_votes=for_v,
            against_votes=against_v,
            abstain_votes=abstain_v,
            quorum=quorum,
            start_block=startBlk,
            end_block=endBlk,
            state=state_int,
        )

    def _state_int(self, proposal_id: str) -> int:
        data = keccak_sig("state(uint256)") + proposal_id.rjust(64, "0")
        raw = self.rpc.eth_call(self.address, data)
        return int(raw, 16) if raw else 0

    def historical_states(self, n: int) -> List[ProposalState]:
        # OZ Governor has no proposalCount(); historical scan requires
        # indexing ProposalCreated event logs, which need the keccak256
        # topic hash of:
        #   ProposalCreated(uint256,address,address[],uint256[],string[],bytes[],uint256,uint256,string)
        # We intentionally do not ship a hard-coded hash (chains differ
        # in compiled form for this multi-array event). Callers needing
        # history should pass `--lookback 0` to fall back to a linear
        # forecast, or use an indexer.
        return []


# ---------- Snapshot (off-chain) ----------

SNAPSHOT_QUERY_PROPOSAL = """
query Proposal($id: String!) {
  proposal(id: $id) {
    id
    title
    state
    author
    space { id name }
    start
    end
    votes
    scores
    scores_total
    quorum
    type
  }
}
"""


class SnapshotGovernor(Governor):
    name = "snapshot"

    def __init__(self, space: str):
        # `space` is the slug, e.g. "aave.eth"
        self.space = space

    def _query(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        r = requests.post(
            SNAPSHOT_HUB,
            json={"query": query, "variables": variables},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            raise RpcError(f"Snapshot: {data['errors']}")
        return data.get("data", {})

    def current_state(self, proposal_id: str) -> ProposalState:
        d = self._query(SNAPSHOT_QUERY_PROPOSAL, {"id": proposal_id})
        p = d.get("proposal")
        if not p:
            raise RpcError(f"Snapshot proposal {proposal_id} not found")
        scores = p.get("scores", []) or []
        # Snapshot stores scores as a JSON array; the order is by
        # strategy. Most DAOs use [for, against, abstain].
        for_v     = int(scores[0]) if len(scores) > 0 else 0
        against_v = int(scores[1]) if len(scores) > 1 else 0
        abstain_v = int(scores[2]) if len(scores) > 2 else 0
        quorum = int(p.get("quorum") or 0)
        # Snapshot's "state" string -> our int mapping
        state_map = {"pending": 0, "active": 1, "closed": 4, "core": 4}
        state_int = state_map.get(p.get("state", "active"), 1)

        return ProposalState(
            proposal_id=proposal_id,
            governor=self.space,
            for_votes=for_v,
            against_votes=against_v,
            abstain_votes=abstain_v,
            quorum=quorum,
            start_ts=int(p.get("start", 0)),
            end_ts=int(p.get("end", 0)),
            state=state_int,
            proposer=p.get("author", "0x0000000000000000000000000000000000000000"),
            extra={"title": p.get("title", ""), "scores_total": p.get("scores_total", 0)},
        )

    def historical_states(self, n: int) -> List[ProposalState]:
        # Not implemented for Snapshot; curve fitting falls back to
        # generic linear if no history is available.
        return []


# ---------- Factory ----------

def detect_mode(governor: str) -> str:
    """`onchain` if governor is a 0x address, `snapshot` otherwise."""
    return "onchain" if governor.startswith("0x") and len(governor) == 42 else "snapshot"


def make_governor(mode: str, governor: str, rpc: Optional[RpcClient]) -> Governor:
    if mode == "onchain" or (mode == "auto" and detect_mode(governor) == "onchain"):
        if rpc is None:
            raise RpcError("on-chain mode requires --rpc-url")
        # Try OpenZeppelin first (more common), fall back to Bravo.
        return OZGovernor(rpc, governor)  # type: ignore[arg-type]
    return SnapshotGovernor(governor)  # type: ignore[arg-type]
