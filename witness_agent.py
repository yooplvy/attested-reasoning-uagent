"""
witness_agent.py - Witnessed-Trades uAgent (Mate Masie feed) - AGENTVERSE-HOSTED single file.

Companion to hosted_agent.py (the attested-reasoning agent). Where that agent
serves PROMISES (bonded reasoning commitments on KommitBridge), this one serves
RECEIPTS: every leveraged paper trade the engines take is witnessed on-chain at
entry and exit on MasieBridge v1.0 (Proof of Witness, VPAY Genesis IP #3) -
irrevocable, anti-backdate, and publicly verifiable against Binance candle data
by anyone with a keccak-256 function.

This agent answers ONLY from chain logs. It maintains an incremental scan
checkpoint in agent storage (free RPC tiers cap eth_getLogs ranges, so it walks
the chain in chunks each interval) and ALWAYS reports its sync window - it
will tell you exactly which blocks it has and hasn't seen. No extrapolation.

Protocol (witness-feed v1.0):
  GetWitnessSummary {}        -> WitnessSummary
  GetRecentWitnesses {n}      -> RecentWitnesses

Verify any reply yourself:
  cast logs --address 0x358c50C1DAe9AD41D0070a3767221F3c191b22F6 \
    --from-block 86969835 --rpc-url https://polygon-bor-rpc.publicnode.com

SPDX-License-Identifier: MIT - EcoVent Africa Limited - VPAY Genesis IP #3
"""

from datetime import datetime, timezone
from typing import List
from uuid import uuid4

import requests
from uagents import Agent, Context, Model, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement, ChatMessage, TextContent, chat_protocol_spec)

# -- chain constants (MasieBridge v1.0 - Polygon Mainnet - source-verified) ----
MASIE = "0x358c50C1DAe9AD41D0070a3767221F3c191b22F6"
DEPLOY_BLOCK = 86969835                      # 2026-05-16 deploy
# topic0 = keccak of the canonical event signatures (from the compiled ABI):
T_OPEN = "0xf34f0495589db8170fe21d2615f53922140e4455e7861f6bb2e79bcc9f652db3"
#         WitnessOpened(bytes32,address,bytes32,int256,uint8,uint8,uint64,bytes32)
T_CLOSE = "0x389833045d479cf65f692b6e9e61088c20a43323050342b58adc1c0525ca5ec9"
#         WitnessClosed(bytes32,int256,uint64,bytes32,int256,uint8)
RPCS = ["https://polygon-bor-rpc.publicnode.com",
        "https://1rpc.io/matic",
        "https://polygon.llamarpc.com",
        "https://polygon.meowrpc.com",
        "https://polygon-rpc.com",
        "https://polygon.drpc.org"]
CHUNK = 4500            # blocks per eth_getLogs call (strictest free tiers cap ~5k)
CHUNKS_PER_RUN = 12     # max chunks each interval tick (be a polite client)


def _rpc(method, params):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    for url in RPCS:
        try:
            r = requests.post(url, json=payload, timeout=15)
            d = r.json()
            if "result" in d and d["result"] is not None:
                return d["result"]
        except Exception:
            continue
    return None


def _latest_block():
    r = _rpc("eth_blockNumber", [])
    return int(r, 16) if r else None


def _scan(ctx: Context):
    """Walk forward from the stored checkpoint, up to CHUNKS_PER_RUN chunks.
    Stores: wa_last (last scanned block), wa_open, wa_close, wa_recent (list)."""
    latest = _latest_block()
    if latest is None:
        ctx.logger.warning("[witness] all RPCs unreachable; will retry")
        return
    last = ctx.storage.get("wa_last") or (DEPLOY_BLOCK - 1)
    opened = ctx.storage.get("wa_open") or 0
    closed = ctx.storage.get("wa_close") or 0
    recent = ctx.storage.get("wa_recent") or []
    # ADAPTIVE chunking: providers cap eth_getLogs ranges anywhere from 50 to
    # 10k blocks. Start optimistic; shrink on refusal; floor at 45. The stored
    # size survives restarts so the agent converges on what its network allows.
    chunk = int(ctx.storage.get("wa_chunk") or CHUNK)
    chunks = 0
    while last < latest and chunks < CHUNKS_PER_RUN:
        frm, to = last + 1, min(last + chunk, latest)
        logs = _rpc("eth_getLogs", [{
            "address": MASIE, "fromBlock": hex(frm), "toBlock": hex(to),
            "topics": [[T_OPEN, T_CLOSE]],
        }])
        if logs is None:
            # try single-topic form (some providers reject OR-arrays)
            logs = []
            ok = True
            for t in (T_OPEN, T_CLOSE):
                part = _rpc("eth_getLogs", [{
                    "address": MASIE, "fromBlock": hex(frm), "toBlock": hex(to),
                    "topics": [t],
                }])
                if part is None:
                    ok = False
                    break
                logs.extend(part)
            if not ok:
                if chunk > 45:
                    chunk = max(45, chunk // 3)
                    ctx.storage.set("wa_chunk", chunk)
                    ctx.logger.warning("[witness] getLogs refused %d-%d; shrinking chunk to %d and retrying next tick" % (frm, to, chunk))
                else:
                    ctx.logger.warning("[witness] getLogs failing even at %d-block chunks - RPC log access blocked from this runtime; stated honestly in replies" % chunk)
                break
        for lg in logs:
            t0 = (lg.get("topics") or [""])[0]
            kind = "OPEN" if t0 == T_OPEN else ("CLOSE" if t0 == T_CLOSE else "?")
            if kind == "OPEN":
                opened += 1
            elif kind == "CLOSE":
                closed += 1
            recent.append({
                "type": kind,
                "trade_id": (lg.get("topics") or ["", ""])[1] if len(lg.get("topics", [])) > 1 else "",
                "tx": lg.get("transactionHash"),
                "block": int(lg.get("blockNumber", "0x0"), 16),
            })
        recent = recent[-12:]
        last = to
        chunks += 1
    ctx.storage.set("wa_last", last)
    ctx.storage.set("wa_open", opened)
    ctx.storage.set("wa_close", closed)
    ctx.storage.set("wa_recent", recent)
    ctx.storage.set("wa_latest_seen", latest)
    ctx.logger.info("[witness] synced to %d/%d - open=%d close=%d - chunk=%d"
                    % (last, latest, opened, closed, chunk))


def _summary_dict(ctx: Context):
    last = ctx.storage.get("wa_last") or (DEPLOY_BLOCK - 1)
    latest = ctx.storage.get("wa_latest_seen") or 0
    return {
        "witnessed_opened": ctx.storage.get("wa_open") or 0,
        "witnessed_closed": ctx.storage.get("wa_close") or 0,
        "synced_from_block": DEPLOY_BLOCK,
        "synced_to_block": last,
        "chain_head_at_last_scan": latest,
        "fully_synced": bool(latest and last >= latest),
        "contract": MASIE,
        "chain": "Polygon Mainnet (137)",
        "note": ("Counts come only from chain logs this agent has actually scanned - "
                 "the sync window is stated so you never mistake partial coverage for "
                 "a total. Every witness is verifiable: keccak(candle bytes) must match "
                 "the stored hash. Don't trust the track record; verify it."),
    }


# -- messages -----------------------------------------------------------------

class GetWitnessSummary(Model):
    pass


class WitnessSummary(Model):
    witnessed_opened: int
    witnessed_closed: int
    synced_from_block: int
    synced_to_block: int
    chain_head_at_last_scan: int
    fully_synced: bool
    contract: str
    chain: str
    note: str


class GetRecentWitnesses(Model):
    n: int = 5


class WitnessRecord(Model):
    type: str
    trade_id: str
    tx: str
    block: int
    polygonscan: str


class RecentWitnesses(Model):
    records: List[WitnessRecord]
    synced_to_block: int
    fully_synced: bool


# -- agent --------------------------------------------------------------------

agent = Agent()

proto = Protocol(name="witness-feed", version="1.0")


@proto.on_message(model=GetWitnessSummary, replies={WitnessSummary})
async def on_summary(ctx: Context, sender: str, _msg: GetWitnessSummary):
    await ctx.send(sender, WitnessSummary(**_summary_dict(ctx)))


@proto.on_message(model=GetRecentWitnesses, replies={RecentWitnesses})
async def on_recent(ctx: Context, sender: str, msg: GetRecentWitnesses):
    recent = ctx.storage.get("wa_recent") or []
    n = max(1, min(int(msg.n or 5), 12))
    recs = [WitnessRecord(
        type=r.get("type", "?"), trade_id=r.get("trade_id", ""),
        tx=r.get("tx", ""), block=r.get("block", 0),
        polygonscan="https://polygonscan.com/tx/" + (r.get("tx") or ""),
    ) for r in recent[-n:]][::-1]
    last = ctx.storage.get("wa_last") or (DEPLOY_BLOCK - 1)
    latest = ctx.storage.get("wa_latest_seen") or 0
    await ctx.send(sender, RecentWitnesses(
        records=recs, synced_to_block=last,
        fully_synced=bool(latest and last >= latest)))


agent.include(proto, publish_manifest=True)


# -- ASI:One chat -------------------------------------------------------------

chat_proto = Protocol(spec=chat_protocol_spec)


def _chat_answer(ctx: Context, text):
    s = _summary_dict(ctx)
    if s["fully_synced"]:
        cover = "full history"
    elif s["synced_to_block"] < s["synced_from_block"]:
        cover = "nothing yet - the log scan has not progressed past the deploy block (RPC log access may be blocked; stated, not hidden)"
    else:
        cover = ("blocks %d to %d (still backfilling - stated, not hidden)"
                 % (s["synced_from_block"], s["synced_to_block"]))
    return ("I serve on-chain trade witnesses from MasieBridge v1.0 (Proof of "
            "Witness, Polygon Mainnet, %s). Scanned %s: %d trades witnessed open, "
            "%d witnessed closed. Every record is irrevocable and verifiable - "
            "keccak of the canonical Binance candle bytes must equal the stored "
            "hash. Ask 'recent' for the latest receipts, or verify yourself: "
            "cast logs --address %s --from-block %d --rpc-url %s"
            % (MASIE, cover, s["witnessed_opened"], s["witnessed_closed"],
               MASIE, DEPLOY_BLOCK, RPCS[0]))


@chat_proto.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(
        timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id))
    text = "".join(c.text for c in msg.content if isinstance(c, TextContent))
    t = (text or "").lower()
    if any(w in t for w in ("built", "purpose", "what are you", "who are you", "about")):
        answer = ("I am the receipts half of a two-agent pair. My sibling @vpay serves "
                  "PROMISES: bonded AI reasoning commitments on KommitBridge. I serve "
                  "RECEIPTS: every leveraged paper trade our engines take is witnessed "
                  "on-chain at entry and exit on MasieBridge v1.0 (%s, Polygon Mainnet) - "
                  "irrevocable, anti-backdate, verifiable by anyone with keccak-256. I "
                  "count only what I have actually scanned and I always state my sync "
                  "window. Say 'recent' for the latest receipts, or 'summary' for counts."
                  % MASIE)
        await ctx.send(sender, ChatMessage(
            timestamp=datetime.now(timezone.utc), msg_id=uuid4(),
            content=[TextContent(type="text", text=answer)]))
        return
    if "recent" in t:
        recent = (ctx.storage.get("wa_recent") or [])[-5:]
        if recent:
            lines = ["%s %s block %d https://polygonscan.com/tx/%s"
                     % (r.get("type"), (r.get("trade_id") or "")[:14],
                        r.get("block", 0), r.get("tx")) for r in recent[::-1]]
            answer = "Latest witnessed trade events:\n" + "\n".join(lines)
        else:
            answer = "No events in my scanned window yet - still backfilling from block %d." % DEPLOY_BLOCK
    else:
        answer = _chat_answer(ctx, text)
    await ctx.send(sender, ChatMessage(
        timestamp=datetime.now(timezone.utc), msg_id=uuid4(),
        content=[TextContent(type="text", text=answer)]))


@chat_proto.on_message(ChatAcknowledgement)
async def on_chat_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


agent.include(chat_proto, publish_manifest=True)


# -- lifecycle ----------------------------------------------------------------

@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info("witness-feed live - address=%s" % ctx.agent.address)
    _scan(ctx)


@agent.on_interval(period=300.0)
async def tick(ctx: Context):
    _scan(ctx)
