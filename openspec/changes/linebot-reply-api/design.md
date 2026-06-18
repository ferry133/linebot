## Context

Today the conversational flow is:

```
LINE → /webhook → MQTT inbox (agents/customer_service/inbox)
     → customer_service agent (_process → _run, ~3-4s incl. Anthropic call)
     → MQTT outbox (gateway/outbox) → gateway _on_outbox → push_line()  ← Push API
```

The gateway is intentionally "pure I/O" and the agent holds the AI logic. The webhook handler (`gateway/line_gateway.py`) currently **discards** `event["replyToken"]`, so the only way to answer is the Push API (`POST /v2/bot/message/push`), which counts against LINE's monthly quota. That quota is exhausted → `HTTP 429 "monthly limit"` → no replies delivered.

Constraints from LINE and from the codebase:
- A reply token is **single-use**, valid only for a short window (~1 min), and one reply call carries up to 5 messages.
- The agent emits **exactly one** outbound message per inbound message (`customer_service.py:237` success / `:243` error — mutually exclusive).
- MQTT inbox/outbox payloads are free-form dicts; `AgentMessage.metadata` is already a free-form dict. No schema to migrate.
- Proactive sends (`trello_line_notifier.py`) push directly and have no reply token.

## Goals / Non-Goals

**Goals:**
- Deliver immediate, inbound-triggered replies via the free Reply API, removing them from the push quota.
- Keep working (via Push fallback) when no reply token exists or the token is expired/used.
- No DB/schema change; backward compatible; no lockstep deploy required.

**Non-Goals:**
- Changing proactive notification delivery (`trello_line_notifier.py` stays on Push).
- Upgrading the LINE plan or batching multiple message bubbles per reply.
- Pre-emptive reply-token expiry detection (we rely on the fallback instead).

## Decisions

**1. Hybrid "Reply-first, Push-fallback" — not a full replacement.**
The Reply API only applies to inbound-triggered replies within a single-use, ~1-min window; proactive messages and slow/expired cases still need Push. So `_on_outbox` tries `reply` when a token is present and falls back to `push` otherwise.
_Alternatives:_ full switch to Reply (rejected — breaks proactive + slow replies); keep Push and upgrade the LINE plan (rejected — recurring cost, leaves the inefficiency in place).

**2. Thread `reply_token` through the existing dict payloads as an optional field.**
Webhook adds `reply_token` to the inbox dict; the agent echoes it in the outbox dict (both success and error paths). No typed schema, no new MQTT topic, no migration.
_Alternative:_ a dedicated typed message field or separate topic (rejected — unnecessary for one optional string).

**3. The gateway owns the reply-vs-push decision; the agent stays I/O-agnostic.**
Preserves the existing "gateway = I/O, agent = logic" separation and keeps LINE credentials only in the gateway.
_Alternative:_ agent calls LINE directly (rejected — violates separation, agent has no LINE token).

**4. Try `reply`; on any non-200, fall back to `push`. No pre-check.**
Simplest and robust; a failed reply call is cheap. The reply-success path returns early so a message is never delivered twice.

## Risks / Trade-offs

- **Slow replies (tool use / Trello round-trips) can outlast the token** → falls back to Push; those still consume quota, but the bulk (quick chats, ~3-4s) become free. Acceptable.
- **Double delivery** → mitigated by returning immediately after a successful `reply`; Push only runs when `reply` returns non-200 or no token is present.
- **Webhook retry reusing a token** → the gateway returns `200` immediately after a non-blocking publish, so LINE does not retry; each token is used once.
- **Future multi-bubble replies** → current design sends one message per token; if more are ever needed, batch into one `reply` call (≤5) or Push the extras.

## Migration Plan

**Deploy:** rebuild the shared `ghcr.io/ferry133/linebot` image (CI sha tag) → bump the image in `jg-base` for **both** `line-gateway` and `customer-service-agent` deployments → `flux reconcile`.

**No lockstep required (backward compatible both ways):**
- Old gateway + new agent → gateway ignores the extra `reply_token`, pushes (today's behavior).
- New gateway + old agent → outbox has no `reply_token`, gateway pushes.
Replies only become free once both run the new image.

**Rollback:** revert the image tag(s). No DB/schema/data changes, so rollback is immediate and lossless.
