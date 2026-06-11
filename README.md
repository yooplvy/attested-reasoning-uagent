# Attested-Reasoning uAgent

**An Agentverse agent whose track record cannot lie.**

Most AI agents *claim* a track record. This one serves a track record that is
cryptographically attested on a public blockchain — and it answers exclusively
from the chain, so it is structurally incapable of exaggerating itself.

Behind it sits **KommitBridge v1.2** (Proof of Reasoning, VPAY Genesis IP #2),
live and source-verified on Polygon Mainnet. An AI trading engine (the NANANOM
council orchestrator) commits every consequential verdict on-chain *before
resolution*: a keccak-256 tuple of `(modelWeightsHash, contextHash, seedCommit,
outputHash)` plus a **10 SOV bond**. For one hour, **anyone on earth may
challenge** the attestation; a successful challenge slashes the bond, with 50%
paid to the challenger as a bounty. Unchallenged attestations finalize and the
bond returns. The full commit → challenge-window → settle cycle runs
autonomously.

> The hashes are the audit — challenge us, or the record stands.

## Live contracts (Polygon Mainnet · chain id 137)

| Contract | Address | Role |
|---|---|---|
| KommitBridge v1.2 | [`0x6B986eF2EFDB5852F1DAa51e450E3ecA86B1590E`](https://polygonscan.com/address/0x6b986ef2efdb5852f1daa51e450e3eca86b1590e#code) | Proof-of-Reasoning registry (source-verified) |
| SovereignToken ($SOV) | `0x5833ABF0Ecfe61e85682F3720BA4d636084e0eC0` | The bond token |

## Quickstart

**Recommended · Agentverse-hosted (24/7, zero infrastructure):**

1. [agentverse.ai](https://agentverse.ai) → **New Agent → Start from Template**
   → any blank/starter Python agent
2. Replace the template code with the contents of **`hosted_agent.py`**
   (single file — the hosted runtime provides `uagents` and `requests`)
3. **Start** the agent. The startup log prints its address and the live
   on-chain attestation count; the protocol manifest publishes automatically.

**Alternative · run it yourself (mailbox/local):**

```bash
pip install -r requirements.txt

# dev (local only):
python3 agent.py

# connected to Agentverse via mailbox (UI flows vary by Agentverse version —
# any path that yields a mailbox key works):
export AGENTVERSE_MAILBOX_KEY=<your key>
export AGENT_SEED="<any long stable private phrase>"
python3 agent.py
```

Smoke-test the chain reader with no agent at all:

```bash
python3 chain.py
```

Demo conversation between two agents:

```bash
# terminal A
python3 agent.py                       # prints its agent address
# terminal B
TARGET=<address> python3 examples/query_client.py
```

## Protocol

| Request | Reply | Meaning |
|---|---|---|
| `GetSummary {}` | `Summary` | total attestations, bond size, challenge window — all `eth_call`s |
| `GetAttestation {attestation_id}` | `Attestation` \| `Error` | the full on-chain struct for one record |
| `GetRecent {n}` | `RecentList` | the latest n records, newest first |

Every reply field is reproducible by any third party with one `eth_call` —
the agent adds discovery and packaging, never authority.

## Verification walkthrough (do not trust this README — run it)

**1 · How many attestations exist?** `nextId` pre-increments (`id = ++nextId`),
so it equals the exact all-time count:

```bash
cast call 0x6B986eF2EFDB5852F1DAa51e450E3ecA86B1590E "nextId()(uint256)" \
  --rpc-url https://polygon.drpc.org
```

**2 · Inspect any attestation** (ids run 1..nextId):

```bash
cast call 0x6B986eF2EFDB5852F1DAa51e450E3ecA86B1590E \
  "attestations(uint256)(uint64,bytes32,bytes32,bytes32,bytes32,address,address,uint256,uint256,uint64,uint8)" \
  1 --rpc-url https://polygon.drpc.org
```

Status codes: 0 Pending · 1 Finalized · 2 Challenged · 3 Revealed · 4 Slashed · 5 Dismissed.

**3 · What is one "attestation cycle"?** commit (`ReasoningAttested` event,
bond locked) → 1h public challenge window → settle (`finalize()` refunds the
bond, emitting `ReasoningFinalized`; or the challenge path resolves it). A
cycle is complete when a record reaches a terminal status (1/4/5). Count
completed cycles yourself: walk ids 1..nextId with the call above and tally
non-Pending records.

**4 · Challenge economics.** Anyone may call `challenge(id)` during the window
by posting a 20 SOV counter-bond. If the replay proves the engine lied about
its own reasoning, the challenger takes 50% of the slashed bond. The absence
of successful slashes *is* the track record.

**5 · The engine cannot rewrite history.** Records are append-only storage on
Polygon; the committed `outputHash` is fixed before the market resolves.
Hindsight editing is cryptographically impossible.

## Why this matters for the agent economy

Agents transacting with agents need trust primitives that don't depend on
reputation scores a counterparty can fabricate. This repo demonstrates the
pattern end-to-end: **bond-backed, challengeable, chain-anchored reasoning
claims**, served over the uAgents protocol so any Agentverse agent can consume
them. Fork it, point `chain.py` at your own attestation registry, and your
agent's claims become challengeable too.

## Repo map

```
agent.py                 the uAgent (mailbox or local) + protocol handlers
chain.py                 stdlib-only Polygon JSON-RPC reader (no web3.py)
examples/query_client.py demo consumer agent
requirements.txt         uagents
LICENSE                  MIT
```

## License

MIT © 2026 EcoVent Africa Limited · Accra, Ghana
Part of VPAY Genesis — *Adwene di adanseɛ: the reasoning attests itself.*
