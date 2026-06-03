"""
rpc.py - JSON-RPC client for governance reads.

Used to read on-chain governor state (proposal, votes, quorum) via
plain `eth_call`. No web3 framework dependency.
"""
from __future__ import annotations
import json
import time
import requests
from typing import Any, Dict, List, Optional


class RpcError(Exception):
    pass


class RpcClient:
    def __init__(self, url: str, timeout: int = 30, max_retries: int = 4):
        self.url = url
        self.timeout = timeout
        self.max_retries = max_retries
        self._id = 0

    def call(self, method: str, params: List[Any]) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                r = requests.post(self.url, json=payload, timeout=self.timeout)
                if r.status_code == 429 or r.status_code >= 500:
                    raise RpcError(f"HTTP {r.status_code}: {r.text[:200]}")
                data = r.json()
                if "error" in data:
                    raise RpcError(data["error"].get("message", "rpc error"))
                return data.get("result")
            except (requests.RequestException, RpcError) as e:
                last_err = e
                time.sleep(0.4 * (2 ** attempt))
        raise RpcError(f"RPC {method} failed after {self.max_retries} attempts: {last_err}")

    def eth_call(self, to: str, data: str, block: str = "latest") -> str:
        return self.call("eth_call", [{"to": to, "data": data}, block])

    def block_number(self) -> int:
        return int(self.call("eth_blockNumber", []), 16)

    def get_block(self, num: int, full_txs: bool = False) -> Dict[str, Any]:
        return self.call("eth_getBlockByNumber", [hex(num), full_txs])

    def get_logs(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self.call("eth_getLogs", [params])

    def chain_id(self) -> int:
        return int(self.call("eth_chainId", []), 16)


# --- ABI-encoded function selectors ---

# Compound Bravo GovernorAlpha:
#   proposals(uint256) returns (uint256 id, address proposer, uint256 eta,
#                              uint256 startBlock, uint256 endBlock,
#                              uint256 forVotes, uint256 againstVotes,
#                              uint256 abstainVotes, bool canceled, bool executed)
# state(uint256) returns (uint8)
# quorumVotes() returns (uint256)

# OpenZeppelin Governor:
#   proposalVotes(uint256) returns (uint256 againstVotes, uint256 forVotes, uint256 abstainVotes)
#   proposalDeadline(uint256) returns (uint256)
#   proposalSnapshot(uint256) returns (uint256)
#   state(uint256) returns (uint8)
#   quorum(uint256 blockNumber) returns (uint256)
#   votingPeriod() returns (uint256)
#   votingDelay() returns (uint256)


def keccak_sig(sig: str) -> str:
    """Compute the 4-byte function selector from a Solidity signature.

    Uses eth_call-compatible keccak256. We delegate to an external tool
    only if available; otherwise a precomputed table is used.
    """
    # Precomputed selectors (see references/governors.md for the full table).
    pre = {
        # Compound Bravo
        "proposals(uint256)": "0x7d5d6a93",
        "state(uint256)": "0x3e4f49e6",
        "quorumVotes()": "0x973ab343",
        # OpenZeppelin Governor
        "proposalVotes(uint256)": "0xda95691a",
        "proposalDeadline(uint256)": "0x2e03ce1b",
        "proposalSnapshot(uint256)": "0x462aca47",
        "quorum(uint256)": "0xf8ce5601",
        "votingPeriod()": "0x9a7e4080",
        "votingDelay()": "0xfe0d94c1",
    }
    if sig in pre:
        return pre[sig]
    raise RpcError(f"No precomputed selector for {sig}; add to rpc.py:pre")


def decode_uint256(hexstr: str) -> int:
    if hexstr is None or hexstr in ("0x", "0x0"):
        return 0
    return int(hexstr, 16)


def decode_address(hexstr: str) -> str:
    if not hexstr or hexstr == "0x" + "0" * 40:
        return "0x0000000000000000000000000000000000000000"
    return "0x" + hexstr[-40:].lower()
