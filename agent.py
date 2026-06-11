"""
agent.py — the Attested-Reasoning uAgent.

An Agentverse-discoverable agent that serves CRYPTOGRAPHICALLY ATTESTED
reasoning records. Every answer it gives is read live from KommitBridge v1.2
on Polygon Mainnet — an on-chain Proof-of-Reasoning registry where an AI
trading engine bonds 10 SOV behind every committed verdict and anyone may
challenge it. The agent cannot exaggerate its track record: the chain is the
only source it answers from.

Protocol (publish_manifest=True → visible on Agentverse):
  GetSummary      -> Summary          (count, bond, window — all chain-read)
  GetAttestation  -> Attestation | Error   (full struct for one id)
  GetRecent       -> RecentList       (latest n attestation records)

Run modes:
  AGENTVERSE_MAILBOX_KEY set  → mailbox agent (shows live on Agentverse)
  unset                       → plain local agent on port 8011 (dev)

Setup (one-time):
  1. pip install -r requirements.txt
  2. agentverse.ai → New Agent → Mailbox → copy the key
  3. export AGENTVERSE_MAILBOX_KEY=<key>
     export AGENT_SEED="<any long private phrase — keep it stable>"
  4. python3 agent.py

SPDX-License-Identifier: MIT · EcoVent Africa Limited · VPAY Genesis IP #2
"""

import os
from typing import List, Optional

from uagents import Agent, Context, Model, Protocol

import chain


# ── message models ──────────────────────────────────────────────────────────

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

SEED = os.environ.get("AGENT_SEED", "attested-reasoning-dev-seed-change-me")
MAILBOX_KEY = os.environ.get("AGENTVERSE_MAILBOX_KEY", "").strip()

if MAILBOX_KEY:
    agent = Agent(name="attested-reasoning", seed=SEED,
                  mailbox=f"{MAILBOX_KEY}@https://agentverse.ai")
else:
    agent = Agent(name="attested-reasoning", seed=SEED,
                  port=8011, endpoint=["http://127.0.0.1:8011/submit"])

proto = Protocol(name="attested-reasoning", version="1.0")


def _summary() -> Optional[Summary]:
    total = chain.total_attestations()
    if total is None:
        return None
    return Summary(
        total_attestations=total,
        bond_per_attestation_sov=chain.bond_amount_sov() or 10.0,
        challenge_window_seconds=chain.challenge_window_s() or 3600,
        contract=chain.KOMMIT_BRIDGE,
        chain="Polygon Mainnet (137)",
        note=("Every record is read live from the chain. Pending records are "
              "challengeable by anyone until the deadline; the bond is slashable. "
              "The hashes are the audit."),
    )


@proto.on_message(model=GetSummary, replies={Summary, Error})
async def on_summary(ctx: Context, sender: str, _msg: GetSummary):
    s = _summary()
    if s is None:
        await ctx.send(sender, Error(reason="all Polygon RPCs unreachable"))
        return
    ctx.logger.info(f"summary -> {sender[:16]}… total={s.total_attestations}")
    await ctx.send(sender, s)


@proto.on_message(model=GetAttestation, replies={Attestation, Error})
async def on_get(ctx: Context, sender: str, msg: GetAttestation):
    rec = chain.get_attestation(msg.attestation_id)
    if rec is None:
        await ctx.send(sender, Error(
            reason=f"attestation {msg.attestation_id} not found (or RPC down)"))
        return
    await ctx.send(sender, Attestation(**rec))


@proto.on_message(model=GetRecent, replies={RecentList, Error})
async def on_recent(ctx: Context, sender: str, msg: GetRecent):
    n = max(1, min(int(msg.n or 3), 10))
    recs = chain.recent_attestations(n)
    if not recs:
        await ctx.send(sender, Error(reason="no records readable (RPC down?)"))
        return
    await ctx.send(sender, RecentList(records=[Attestation(**r) for r in recs]))


agent.include(proto, publish_manifest=True)


@agent.on_interval(period=3600.0)
async def heartbeat(ctx: Context):
    """Hourly chain-truth log line — proof-of-life in the Agentverse logs."""
    total = chain.total_attestations()
    ctx.logger.info(
        f"[attested-reasoning] chain-read heartbeat · attestations={total} "
        f"· contract={chain.KOMMIT_BRIDGE}")


@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"address: {agent.address}")
    s = _summary()
    if s:
        ctx.logger.info(
            f"KommitBridge live · {s.total_attestations} attestations · "
            f"{s.bond_per_attestation_sov:.0f} SOV bond · "
            f"{s.challenge_window_seconds}s challenge window")
    else:
        ctx.logger.warning("Polygon RPCs unreachable at startup (will retry on queries)")


if __name__ == "__main__":
    agent.run()
