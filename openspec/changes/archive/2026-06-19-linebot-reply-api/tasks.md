## 1. Gateway — capture & forward the reply token

- [x] 1.1 In `gateway/line_gateway.py` `webhook()` (~:128), read `event.get("replyToken")` and add `"reply_token": <token>` to the inbox payload published to `agents/customer_service/inbox`.

## 2. Agent — thread the reply token through

- [x] 2.1 In `agents/customer_service.py` `_on_message` (:225), read `reply_token = payload.get("reply_token")` and pass it into `_process`.
- [x] 2.2 In `_process` (:234), include `"reply_token": reply_token` in **both** outbox publishes — success (:237) and error fallback (:243).

## 3. Gateway — Reply-first delivery with Push fallback

- [x] 3.1 Add `reply_line(reply_token: str, text: str) -> bool` calling `POST https://api.line.me/v2/bot/message/reply` with `{"replyToken", "messages":[{type:text,text}]}`; return `False` and log on non-200.
- [x] 3.2 Rework `_on_outbox` (:86): skip if `content` empty; if `reply_token` present and `reply_line(...)` returns `True`, return (do not push); otherwise `push_line(user_id, content)`.

## 4. Verify locally

- [x] 4.1 Test that a webhook event with a `replyToken` yields an inbox payload containing `reply_token`, and the agent echoes it into the outbox payload.
- [x] 4.2 Test `_on_outbox` (mock `requests`): token present + reply 200 ⇒ only `message/reply` called; token absent ⇒ `message/push` called; reply non-200 ⇒ falls back to `message/push`.
- [x] 4.3 Confirm the proactive path (`trello_line_notifier.py`) is untouched — still uses `message/push`.

## 5. Deploy & validate in cluster

- [x] 5.1 Commit & push `linebot`; let CI build the sha-tagged image.
- [x] 5.2 Bump the image tag for **both** `line-gateway` and `customer-service-agent` deployments in `jg-base`; `flux reconcile`.
- [x] 5.3 Send a test LINE message; confirm `line-gateway` logs show a successful reply (no `429`) and the reply arrives in LINE.
