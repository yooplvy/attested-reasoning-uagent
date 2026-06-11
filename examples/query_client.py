"""
examples/query_client.py — a second uAgent that interrogates the
Attested-Reasoning agent and prints what the chain says.

Usage:
  1. Terminal A:  python3 agent.py          (note the printed agent address)
  2. Terminal B:  TARGET=<that address> python3 examples/query_client.py

The point of the demo: agent B receives a reasoning track record it does NOT
have to trust — every field is independently re-checkable on Polygonscan.

SPDX-License-Identifier: MIT
"""

import os
import sys

from uagents import Agent, Context, Model
from typing import List


class GetSummary(Model):
    pass


class Summary(Model):
    total_attestations: int
    bond_per_attestation_sov: float
    challenge_window_seconds: int
    contract: str
    chain: str
    note: str


class GetRecent(Model):
    n: int = 3


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


class RecentList(Model):
    records: List[Attestation]


class Error(Model):
    reason: str


TARGET = os.environ.get("TARGET", "").strip()
if not TARGET:
    sys.exit("set TARGET=<attested-reasoning agent address> (printed at its startup)")

client = Agent(name="ar-client", seed="ar-demo-client-seed",
               port=8012, endpoint=["http://127.0.0.1:8012/submit"])


@client.on_event("startup")
async def go(ctx: Context):
    ctx.logger.info(f"asking {TARGET[:20]}… for the attested track record")
    await ctx.send(TARGET, GetSummary())
    await ctx.send(TARGET, GetRecent(n=3))


@client.on_message(model=Summary)
async def on_summary(ctx: Context, sender: str, msg: Summary):
    ctx.logger.info(
        f"SUMMARY · {msg.total_attestations} attestations · "
        f"{msg.bond_per_attestation_sov:.0f} SOV bonded each · {msg.chain} · {msg.contract}")


@client.on_message(model=RecentList)
async def on_recent(ctx: Context, sender: str, msg: RecentList):
    for r in msg.records:
        ctx.logger.info(
            f"  #{r.id} · {r.status} · output {r.output_hash[:18]}… · "
            f"bond {r.reasoner_bond_sov:.0f} SOV · "
            f"{'CHALLENGEABLE NOW' if r.challenge_open else 'window closed'}")


@client.on_message(model=Error)
async def on_err(ctx: Context, sender: str, msg: Error):
    ctx.logger.warning(f"error from agent: {msg.reason}")


if __name__ == "__main__":
    client.run()
