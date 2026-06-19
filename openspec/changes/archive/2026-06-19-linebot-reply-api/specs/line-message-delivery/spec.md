## ADDED Requirements

### Requirement: Immediate replies use the LINE Reply API

When delivering a reply that was triggered by an inbound user message, the system SHALL use the LINE Reply API (`POST /v2/bot/message/reply`) with that message's reply token, so the reply does not consume the monthly push quota. A given reply token SHALL be used at most once, and the agent SHALL emit exactly one outbound message per inbound message.

#### Scenario: Reply delivered for free within the validity window
- **WHEN** a user sends a text message and the agent produces its reply while the reply token is still valid and unused
- **THEN** the gateway delivers the reply via `message/reply` using that reply token
- **AND** no push-message quota is consumed

#### Scenario: Error reply also uses the reply token
- **WHEN** the agent fails to process an inbound message and emits its fallback error text
- **THEN** that error reply is delivered via `message/reply` using the same reply token

### Requirement: Fallback to the Push API

The system SHALL fall back to the Push API (`POST /v2/bot/message/push`) to deliver an outbound message to the user when no reply token is available, or when the Reply API call does not succeed (for example, the token has expired or has already been used).

#### Scenario: No reply token present
- **WHEN** an outbound message has no associated reply token
- **THEN** the gateway delivers it via `message/push` to the user id

#### Scenario: Reply token expired or already used
- **WHEN** the gateway attempts `message/reply` and LINE returns a non-success response
- **THEN** the gateway delivers the same message via `message/push` to the user id

### Requirement: Reply token propagation through the delivery pipeline

The gateway SHALL capture the `replyToken` from each inbound message event and propagate it through the inbox → agent → outbox path, so the component that produces the reply can request Reply-API delivery.

#### Scenario: Token threaded from webhook to outbox
- **WHEN** the gateway receives a webhook message event carrying a `replyToken`
- **THEN** the gateway includes that token in the inbox payload published to the agent
- **AND** the agent echoes the same token in the outbox payload it publishes back

### Requirement: Proactive messages use the Push API

Messages that are not triggered by an inbound user message — and therefore have no reply token — SHALL be delivered via the Push API.

#### Scenario: Proactive notification is pushed
- **WHEN** a proactive message is sent (for example, a daily summary or a Trello notification)
- **THEN** it is delivered via `message/push`
