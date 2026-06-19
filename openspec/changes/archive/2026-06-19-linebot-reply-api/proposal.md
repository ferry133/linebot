## Why

The bot's conversational replies are delivered through LINE's **Push API**, which counts against the LINE account's monthly message quota. That quota is now exhausted — every reply fails with `HTTP 429 "You have reached your monthly limit"`, so users who message the bot get no response. LINE's **Reply API** (reply token) is free and unlimited for replying to an inbound message, so moving immediate replies onto it both fixes the current outage and prevents it from recurring.

## What Changes

- The gateway captures the webhook `replyToken` and threads it through MQTT (inbox → agent → outbox).
- Outbound delivery **prefers the free Reply API** (`message/reply`) when a reply token is present, and **falls back to the Push API** (`message/push`) when there is no token or the reply call fails (token expired/already used).
- Proactive / unprompted messages (Trello notifications, daily summaries via `trello_line_notifier.py`) keep using Push — they have no reply token. Unchanged.
- The MQTT inbox/outbox payloads gain an optional `reply_token` field. No DB or schema migration; backward compatible (absent token ⇒ today's push behavior).

## Capabilities

### New Capabilities
- `line-message-delivery`: How the bot delivers outbound LINE messages — preferring the free Reply API for an immediate reply to an inbound user message (single-use reply token, used within its validity window), and using the Push API both for proactive messages and as the fallback when no usable reply token is available.

### Modified Capabilities
_None — no existing spec covers outbound message delivery. `line-user-registry` covers inbound user registration only._

## Impact

- **Code**:
  - `gateway/line_gateway.py` — webhook forwards `replyToken`; `_on_outbox` gains reply-then-push logic; new `reply_line()` helper calling `POST /v2/bot/message/reply`.
  - `agents/customer_service.py` — `_on_message` / `_process` carry `reply_token` into the outbox payload (both success and error paths).
- **MQTT envelope**: inbox and outbox dict payloads gain an optional `reply_token` (free-form, no schema change).
- **External API**: adds LINE `POST /v2/bot/message/reply`; retains `POST /v2/bot/message/push`.
- **Deployment**: rebuild the shared `ghcr.io/ferry133/linebot` image; roll both `line-gateway` and `customer-service-agent` deployments.
- **No** DB changes, **no** new dependencies.
