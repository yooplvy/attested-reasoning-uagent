"""
chain.py — stdlib-only Polygon reader for KommitBridge v1.2 (Proof of Reasoning).

No web3.py dependency: raw JSON-RPC over urllib so the agent runs anywhere
Python runs (including minimal hosts). Every byte returned by these helpers
comes from the chain — the agent never invents a number.

Contract: KommitBridge v1.2 · Polygon Mainnet (chain id 137)
  0x6B986eF2EFDB5852F1DAa51e450E3ecA86B1590E
  source-verified: https://polygonscan.com/address/0x6b986ef2efdb5852f1daa51e450e3eca86b1590e#code

Function selectors (keccak-256 of the canonical signature, first 4 bytes —
recompute with `cast sig` or Web3.keccak to verify):
  nextId()                 0x61b8ce8c   (== total attestations; ids are 1-based)
  attestations(uint256)    0x01daf26b
  reasonerBondAmount()     0x100d0b50
  challengeWindow()        0x861a1412

SPDX-License-Identifier: MIT
"""

import json
import time
import urllib.request
from typing import Any, Dict, List, Optional

KOMMIT_BRIDGE = "0x6B986eF2EFDB5852F1DAa51e450E3ecA86B1590E"
CHAIN_ID = 137

# Public RPCs, tried in order. drpc first (reachable from West-African ISPs
# where several other public endpoints are not).
RPC_URLS = [
    "https://polygon.drpc.org",
    "https://polygon-bor-rpc.publicnode.com",
    "https://polygon-rpc.com",
]

SEL_NEXT_ID = "0x61b8ce8c"
SEL_ATTESTATIONS = "0x01daf26b"
SEL_BOND = "0x100d0b50"
SEL_WINDOW = "0x861a1412"

STATUS_NAMES = {
    0: "Pending",      # within challenge window
    1: "Finalized",    # window elapsed unchallenged — bond refunded
    2: "Challenged",   # challenge active, awaiting seed reveal
    3: "Revealed",     # seed revealed, awaiting oracle verdict / default
    4: "Slashed",      # reasoner slashed
    5: "Dismissed",    # challenger bond forfeited
}


def _rpc_call(data: str, timeout: float = 15.0) -> Optional[str]:
    """eth_call against KommitBridge, with RPC fallback. Returns hex or None."""
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": KOMMIT_BRIDGE, "data": data}, "latest"],
    }).encode()
    for url in RPC_URLS:
        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json",
                         "User-Agent": "attested-reasoning-uagent/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                out = json.loads(resp.read())
            if out.get("result"):
                return out["result"]
        except Exception:
            continue
    return None


def _word(hexstr: str, i: int) -> str:
    """The i-th 32-byte word of an ABI-encoded return blob (no 0x prefix)."""
    body = hexstr[2:] if hexstr.startswith("0x") else hexstr
    return body[i * 64:(i + 1) * 64]


def total_attestations() -> Optional[int]:
    """nextId() — increments BEFORE assignment (id = ++nextId), so this IS the
    exact all-time count and live ids run 1..nextId inclusive."""
    r = _rpc_call(SEL_NEXT_ID)
    return int(r, 16) if r and r != "0x" else None


def bond_amount_sov() -> Optional[float]:
    r = _rpc_call(SEL_BOND)
    return int(r, 16) / 1e18 if r and r != "0x" else None


def challenge_window_s() -> Optional[int]:
    r = _rpc_call(SEL_WINDOW)
    return int(r, 16) if r and r != "0x" else None


def get_attestation(attestation_id: int) -> Optional[Dict[str, Any]]:
    """attestations(uint256) — decoded struct, or None if absent/unreachable."""
    arg = format(attestation_id, "064x")
    r = _rpc_call(SEL_ATTESTATIONS + arg)
    if not r or len(r) < 2 + 11 * 64:
        return None
    reasoner = "0x" + _word(r, 5)[24:]
    if int(reasoner, 16) == 0:
        return None  # never written
    status = int(_word(r, 10), 16)
    deadline = int(_word(r, 9), 16)
    return {
        "id": attestation_id,
        "timestamp": int(_word(r, 0), 16),
        "model_weights_hash": "0x" + _word(r, 1),
        "context_hash": "0x" + _word(r, 2),
        "seed_commit": "0x" + _word(r, 3),
        "output_hash": "0x" + _word(r, 4),
        "reasoner": reasoner,
        "reasoner_bond_sov": int(_word(r, 7), 16) / 1e18,
        "challenge_deadline": deadline,
        "challenge_open": status == 0 and time.time() < deadline,
        "status": STATUS_NAMES.get(status, str(status)),
        "polygonscan": ("https://polygonscan.com/address/"
                        + KOMMIT_BRIDGE + "#readContract"),
    }


def recent_attestations(n: int = 5) -> List[Dict[str, Any]]:
    total = total_attestations()
    if not total:
        return []
    out = []
    for aid in range(total, max(0, total - n), -1):
        rec = get_attestation(aid)
        if rec:
            out.append(rec)
    return out


if __name__ == "__main__":  # smoke test: python3 chain.py
    print("total attestations:", total_attestations())
    print("bond (SOV):", bond_amount_sov())
    print("challenge window (s):", challenge_window_s())
    for rec in recent_attestations(2):
        print(json.dumps(rec, indent=2))
