"""
hosted_agent.py — Attested-Reasoning uAgent · AGENTVERSE-HOSTED single file.

Paste this entire file into an Agentverse hosted agent (New Agent → Start from
Template → blank/starter Python agent → replace the code → Start). Hosted
agents run 24/7 on Agentverse infrastructure: no local machine, no mailbox.

What it does: serves CRYPTOGRAPHICALLY ATTESTED reasoning records, read live
from KommitBridge v1.2 (Proof of Reasoning) on Polygon Mainnet. An AI trading
engine bonds 10 SOV behind every committed verdict; anyone may challenge a
record during its 1-hour window and take 50% of the slashed bond if the engine
lied. This agent answers ONLY from the chain — it cannot exaggerate.

Protocol:
  GetSummary {}                -> Summary
  GetAttestation {attestation_id} -> Attestation | Error
  GetRecent {n}                -> RecentList

Verify any reply yourself (the agent adds discovery, never authority):
  cast call 0x6B986eF2EFDB5852F1DAa51e450E3ecA86B1590E "nextId()(uint256)" \
    --rpc-url https://polygon.drpc.org

SPDX-License-Identifier: MIT · EcoVent Africa Limited · VPAY Genesis IP #2
"""

import time
from typing import List

import requests
from uagents import Agent, Context, Model, Protocol

# ── chain constants (KommitBridge v1.2 · Polygon Mainnet · source-verified) ──
KOMMIT = "0x6B986eF2EFDB5852F1DAa51e450E3ecA86B1590E"
RPCS = ["https://polygon.drpc.org",
        "https://polygon-bor-rpc.publicnode.com",
        "https://polygon-rpc.com"]
SEL_NEXT_ID = "0x61b8ce8c"        # nextId()            == exact all-time count
SEL_ATTESTATIONS = "0x01daf26b"   # attestations(uint256)
SEL_BOND = "0x100d0b50"           # reasonerBondAmount()
SEL_WINDOW = "0x861a1412"         # challengeWindow()
STATUS = {0: "Pending", 1: "Finalized", 2: "Challenged",
          3: "Revealed", 4: "Slashed", 5: "Dismissed"}


def _call(data):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
               "params": [{"to": KOMMIT, "data": data}, "latest"]}
    for url in RPCS:
        try:
            r = requests.post(url, json=payload, timeout=12)
            out = r.json()
            if out.get("result"):
                return out["result"]
        except Exception:
            continue
    return None


def _word(h, i):
    b = h[2:] if h.startswith("0x") else h
    return b[i * 64:(i + 1) * 64]


def _total():
    r = _call(SEL_NEXT_ID)
    return int(r, 16) if r and r != "0x" else None


def _record(aid):
    r = _call(SEL_ATTESTATIONS + format(aid, "064x"))
    if not r or len(r) < 2 + 11 * 64:
        return None
    reasoner = "0x" + _word(r, 5)[24:]
    if int(reasoner, 16) == 0:
        return None
    st = int(_word(r, 10), 16)
    dl = int(_word(r, 9), 16)
    return dict(
        id=aid,
        timestamp=int(_word(r, 0), 16),
        model_weights_hash="0x" + _word(r, 1),
        context_hash="0x" + _word(r, 2),
        seed_commit="0x" + _word(r, 3),
        output_hash="0x" + _word(r, 4),
        reasoner=reasoner,
        reasoner_bond_sov=int(_word(r, 7), 16) / 1e18,
        challenge_deadline=dl,
        challenge_open=(st == 0 and time.time() < dl),
        status=STATUS.get(st, str(st)),
        polygonscan="https://polygonscan.com/address/" + KOMMIT + "#readContract",
    )


# ── messages ────────────────────────────────────────────────────────────────

class GetSummary(Model):
    pass


class Summary(Model):
    total_attestations: int
    bond_per_attestation_sov: float
    challenge_window_seconds: int
    contract: str
    chain: str
    note: str


class GetAttestation(Model):
    attestation_id: int


class Attestation(Model):
    id: int
    timestamp: int
    model_weights_hash: str
    context_hash: str
    seed_commit: str
    output_hash: str
    reasoner: str
    reasoner_bond_sov: float
    challenge_deadline: int
    challenge_open: bool
    status: str
    polygonscan: str


class GetRecent(Model):
    n: int = 3


class RecentList(Model):
    records: List[Attestation]


class Error(Model):
    reason: str


# ── agent ───────────────────────────────────────────────────────────────────
# NOTE: hosted agents ignore name/seed kwargs supplied here in some runtimes —
# Agentverse manages identity. Keeping the constructor minimal is deliberate.
agent = Agent()

proto = Protocol(name="attested-reasoning", version="1.0")


@proto.on_message(model=GetSummary, replies={Summary, Error})
async def on_summary(ctx: Context, sender: str, _msg: GetSummary):
    total = _total()
    if total is None:
        await ctx.send(sender, Error(reason="all Polygon RPCs unreachable"))
        return
    bond = _call(SEL_BOND)
    win = _call(SEL_WINDOW)
    await ctx.send(sender, Summary(
        total_attestations=total,
        bond_per_attestation_sov=(int(bond, 16) / 1e18) if bond else 10.0,
        challenge_window_seconds=int(win, 16) if win else 3600,
        contract=KOMMIT,
        chain="Polygon Mainnet (137)",
        note=("Chain-read only. Pending records are publicly challengeable "
              "until the deadline; the bond is slashable. The hashes are the audit."),
    ))


@proto.on_message(model=GetAttestation, replies={Attestation, Error})
async def on_get(ctx: Context, sender: str, msg: GetAttestation):
    rec = _record(msg.attestation_id)
    if rec is None:
        await ctx.send(sender, Error(
            reason="attestation %d not found (or RPC down)" % msg.attestation_id))
        return
    await ctx.send(sender, Attestation(**rec))


@proto.on_message(model=GetRecent, replies={RecentList, Error})
async def on_recent(ctx: Context, sender: str, msg: GetRecent):
    total = _total()
    if not total:
        await ctx.send(sender, Error(reason="RPC unreachable"))
        return
    n = max(1, min(int(msg.n or 3), 10))
    recs = []
    for aid in range(total, max(0, total - n), -1):
        rec = _record(aid)
        if rec:
            recs.append(Attestation(**rec))
    await ctx.send(sender, RecentList(records=recs))


agent.include(proto, publish_manifest=True)


@agent.on_interval(period=3600.0)
async def heartbeat(ctx: Context):
    ctx.logger.info("[attested-reasoning] heartbeat · attestations=%s · %s"
                    % (_total(), KOMMIT))


@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info("attested-reasoning live · address=%s" % ctx.agent.address)
    ctx.logger.info("KommitBridge attestations=%s" % _total())
