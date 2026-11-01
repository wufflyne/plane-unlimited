# plane-unlimited

Self-hosted [Plane](https://plane.so) (commercial edition, v4.0.1) with an
offline ENTERPRISE license and all cloud-only noise removed.

Base image: `makeplane/plane-aio-commercial:stable` (v4.0.1) — the
all-in-one image (web, space, admin, API, workers, live, silo, email, proxy
under one supervisor).

## What this does

- **ENTERPRISE, offline.** The commercial edition verifies short-lived license
  grants against Ed25519 trust anchors shipped inside the image. This build
  swaps those anchors for its own key pair and seeds an INSTANCE-scoped grant
  (tier `ENTERPRISE`, 1,000,000 seats, valid until 2100, `airgapped: true`)
  on every boot via `manage.py unlimited_seed`. The grant passes the stock
  `verify_grant()` check, so every feature-gating path in the app sees a
  genuine Enterprise license. No code in Plane itself is modified.
- **No phone-home.** `PRIME_HOST` / `PAYMENT_SERVER_BASE_URL` point at a dead
  local address, `IS_AIRGAPPED=1`, telemetry is force-disabled on boot,
  version-check / changelog / grant-refresh tasks fail silently offline, and
  LocalStack's own telemetry is disabled (`DISABLE_EVENTS=1`). Verified with
  packet captures: the stack makes no outbound connections.
- **No cloud upsell in the UI.** "Contact sales" entries and the god-mode
  telemetry / cloud-chat settings rows are dead-coded out of the prebuilt JS
  bundles at build time (`unlimited_strip_ui.py`). The air-gap license page is
  kept — it shows the Enterprise license and is fully functional.

## Install path A — pull the ready image

```bash
cp .env.example .env
# edit .env: set SECRET_KEY and DB_PASSWORD (generate with openssl rand -hex 24/16)
docker compose up -d
```

Then open `http://localhost:8090` (or the `WEB_PORT` you chose). First boot
runs the full migration set (~15 minutes on modest hardware); afterwards the
API registers the instance fully offline, seeds the license, and the UI comes
up. Create the admin account via the god-mode sign-up page on first visit.

## Install path B — build from source

```bash
cp .env.example .env                  # edit as above
scripts/build.sh                      # builds plane-unlimited:local
# set PLANE_IMAGE=plane-unlimited:local in .env
docker compose up -d
```

The build downloads `makeplane/plane-aio-commercial:stable`, swaps the
license trust anchors, installs the seed command and applies the UI/RabbitMQ
patches. `scripts/build.sh [tag]` builds any tag; `stable` is the published release tag.

## Configuration

All runtime configuration lives in `.env` (see `.env.example`):

| Variable | Meaning |
| --- | --- |
| `SECRET_KEY` | Django session/crypto secret. **Must** be set — generate with `openssl rand -hex 24`. |
| `DB_PASSWORD` | Internal Postgres + RabbitMQ password. Generate with `openssl rand -hex 16`. |
| `WEB_PORT` | Host port for the web UI (default `8090`). |
| `DOMAIN_NAME` | Hostname users reach the instance at (no scheme). |
| `PLANE_IMAGE` | Image to run; defaults to `wufflyne/plane-unlimited:stable`, set `plane-unlimited:local` after a local build. |

## Repository layout

- `Dockerfile` — builds the image from the base image: swaps trust anchors
  (public key in `keys/`), installs `unlimited_seed.py` and
  `unlimited_strip_ui.py` into the image, hooks the seed into the API
  entrypoint.
- `docker-compose.yml` / `.env.example` — user deployment: postgres 17,
  redis 7, rabbitmq 4, localstack (free community 4.x, S3) and plane.
- `unlimited_seed.py` — Django management command; idempotent. Forges the
  grant for the current instance, widens `license_grants.token` to `text`,
  upserts the grant, syncs workspace license rows (ENTERPRISE, 1M seats) and
  disables telemetry. Runs on every API boot.
- `unlimited_strip_ui.py` — patches the prebuilt web/admin JS bundles at image
  build time (removes cloud-only menu entries and settings rows) and applies
  RabbitMQ 4.x compatibility patches.
- `unlimited_signing_key.pem` — private Ed25519 key that signs the forged
  grant. Replace it (and `keys/`) to rotate.
- `keys/` — the public key installed as the trust anchors
  (`plane-licence-prod-20261021.pem` etc., filenames preserved because the
  grant `kid` is the filename stem).
- `scripts/generate-keys.sh` — generate/rotate the signing key pair.
- `scripts/build.sh` — build the image locally.
- `rabbitmq.conf` — allows the transient non-exclusive classic queues Plane
  declares (RabbitMQ >= 4.1 rejects them by default; without this, silo and
  live-exporter crash-loop).
- `localstack-init.sh` — creates the `plane` S3 bucket on first boot.
- `docs/` — design notes and the license/legal caveat.

## Signing key handling

The `unlimited_signing_key.pem` in this repo is deliberately **not treated as
a secret**: it only ever signs the ENTERPRISE grant for instances booted from
this image, and its public half must match the trust anchors baked in. Every
user's deployment accepts grants from this key — if you want your instance to
only accept grants you signed yourself, run `scripts/generate-keys.sh` and use
install path B. The shipped key is in no way a credential to anything else.

## Upgrading

Pull the new base tag, rebuild, restart:

```bash
docker compose pull plane
scripts/build.sh
docker compose up -d
```

Upstream image updates re-introduce the stock trust anchors and UI bundles; the
build re-applies all patches (and fails loudly if an upstream asset changed
in a way a patch no longer matches).

## FAQ

**First boot takes forever — is it stuck?**
No. The full Django migration set runs on first boot, which takes roughly
15 minutes on modest hardware. Watch progress with
`docker compose logs -f plane`. Subsequent boots are fast.

**I can't create the admin account — my password is rejected.**
The god-mode sign-up page enforces a strong password policy (length and
character mix). Use a long generated password, e.g. `openssl rand -base64 18`.

**My instance is on a non-standard port and links/emails point at the wrong URL.**
`DOMAIN_NAME` must be a bare hostname or IP (no scheme, no port) — the startup
script validates it. Use `WEB_PORT` for the port. With a non-standard port a
few god-mode form redirects can land on port 80; re-open the page on your
port — the app itself is unaffected.

**How do I know it's really offline?**
The stack makes no outbound connections — this was verified with packet
captures during development. All licensing endpoints point at a dead local
address, telemetry is off, and `IS_AIRGAPPED=1` uses Plane's own air-gap
registration path.

## Notes & limitations

- The FIPS image variants (`*-commercial-fips`) use ECDSA P-256 instead of
  Ed25519; this build targets the standard images.
- Plane's own code logs a harmless `RuntimeWarning` about a naive datetime
  when it converts the grant's period end — cosmetic, comes from upstream.
- See `docs/LEGAL.md` before redistributing: the base image is Plane's
  closed-source commercial edition.

## License

Scripts, patches and docs in this repo are MIT (see `LICENSE.md`). Plane and
the commercial base image are © Plane.so / Makeplane under their own terms;
this project is unofficial and not affiliated with Plane.

---

Built by [wufflyne](https://wufflyne.com).
