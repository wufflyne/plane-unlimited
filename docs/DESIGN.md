# Design notes

## How the license works

The commercial edition verifies short-lived JWS grants (`plane-grant+jws`,
Ed25519) against a trust store of public keys in
`/app/backend/plane/license/trust/keys/` — the grant's `kid` is the filename
stem of the matching anchor. plane-unlimited:

1. replaces both shipped anchors with its own public key (same filenames),
2. bakes in the matching private key at
   `/app/backend/plane/unlimited_signing_key.pem`,
3. appends `manage.py unlimited_seed` to the API entrypoint. On every boot it
   forges an INSTANCE-scoped ENTERPRISE grant for the current `instance_id`
   and stores it after verifying it through the stock `verify_grant()`.

The seed is idempotent, serialized via a Postgres advisory lock, and takes a
fast path when a valid grant is already stored.

## Offline behaviour

`IS_AIRGAPPED=1` makes `register_instance_ee` register the instance without
calling Prime. `PRIME_HOST`, `PAYMENT_SERVER_BASE_URL` and
`INSTANCE_CHANGELOG_URL` point at `http://127.0.0.1:1` so any background
refresh/version-check task fails fast instead of hanging; the stored grant is
kept. `OTEL_ENABLED=0` disables OTLP export. Verified with packet captures
(see the build logs): no outbound connections.

## UI stripping

`unlimited_strip_ui.py` runs at build time and asserts each replacement
matches exactly once, so an upstream asset rename fails the build loudly
instead of silently shipping the upsell UI. Patched: web help-menu
"Contact Sales" (mailto), sidebar "Contact sales", god-mode "Chat +
telemetry" section, plus the telemetry sentence in its page description.

## RabbitMQ 4.x

Plane's Node services assume RabbitMQ 3.x defaults:

- `rabbitmq.conf` permits `transient_nonexcl_queues` (RabbitMQ >= 4.1
  otherwise rejects Plane's transient non-exclusive classic queues, crash-
  looping silo / live-exporter);
- the live-exporter `x-consumer-timeout` queue argument (rejected by 4.x) is
  removed;
- the Node amqplib programs get `?frameMax=8192` appended to their
  `AMQP_URL` via supervisor env substitution (amqplib defaults to 4096,
  which RabbitMQ 4.x rejects at connection negotiation).

## Hardening notes

- `SECRET_KEY` and `DB_PASSWORD` are required in `.env` (compose fails fast
  with a `:?` error if unset) — no default credentials ship in the compose.
- No secrets exist in image layers beyond the licence-signing key, which is
  not a credential to anything external (see README "Signing key handling").
- LocalStack is pinned to the free community 4.x image (S3-only) with its
  telemetry disabled.
