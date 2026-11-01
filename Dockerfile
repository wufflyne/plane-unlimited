# plane-unlimited: patched Plane Commercial All-In-One
#
# Base: stock makeplane/plane-aio-commercial:stable (v4.0.1). All changes are
# additive (no .pyc patching):
#   1. trust anchors: both shipped plane-licence-prod-*.pem are replaced with
#      OUR Ed25519 public key (filenames kept; kid = filename stem),
#   2. the private signing key is baked in so every boot can re-forge the
#      INSTANCE-scoped ENTERPRISE grant for the current instance_id,
#   3. the Django command `unlimited_seed` is installed and appended to the
#      API entrypoint: after `manage.py startup commercial` it forges, verifies
#      (real verify_grant) and loads the grant, syncs WorkspaceLicense rows and
#      turns instance telemetry off. Idempotent; safe on first boot,
#   4. UI stripping at build time (`unlimited_strip_ui.py`): web help-menu
#      "Contact Sales" and god-mode "Chat + telemetry" dead-coded, plus
#      RabbitMQ 4.x compatibility patches for the Node services,
#   5. offline by construction: IS_AIRGAPPED=1 registers the instance via the
#      built-in air-gap path (register_instance_ee never calls Prime), and
#      PRIME_HOST / PAYMENT_SERVER_BASE_URL / INSTANCE_CHANGELOG_URL point at a
#      dead local endpoint so refresh/version/changelog tasks fail fast and
#      keep the stored grant. OTEL_ENABLED=0 disables OTLP egress.
#
# Author: wufflyne <wufflyne@proton.me> — wufflyne.com
FROM makeplane/plane-aio-commercial:stable

# --- offline env first: static, never changes -------------------------------
ENV IS_AIRGAPPED=1 \
    PRIME_HOST=http://127.0.0.1:1 \
    PAYMENT_SERVER_BASE_URL=http://127.0.0.1:1 \
    INSTANCE_CHANGELOG_URL=http://127.0.0.1:1 \
    OTEL_ENABLED=0

# --- trust anchors (kid = filename stem, both kept consistent) ---------------
COPY keys/plane-licence-prod-20261021.pem /app/backend/plane/license/trust/keys/plane-licence-prod-20261021.pem
COPY keys/plane-licence-prod-202610.pem   /app/backend/plane/license/trust/keys/plane-licence-prod-202610.pem

# --- our signing key (NOT inside trust/keys/ which rejects private keys) -----
# The API entrypoint later drops to the unprivileged `plane` user; the copied
# key keeps its world-readable 0644 mode so loading it always works.
COPY unlimited_signing_key.pem /app/backend/plane/unlimited_signing_key.pem

# --- S3Storage fix (sitecustomize is imported by every Python process) -------
# Plane's S3Storage.__init__ skips S3Boto3Storage.__init__, which leaves
# `location` unset and breaks Django FileField saves. See patches/sitecustomize.py.
COPY patches/sitecustomize.py /usr/local/lib/python3.12/site-packages/sitecustomize.py

# --- seed command + entrypoint hook ------------------------------------------
COPY unlimited_seed.py /app/backend/plane/license/management/commands/unlimited_seed.py
RUN sed -i 's|^python manage.py startup commercial$|python manage.py startup commercial\n\n# plane-unlimited: forge \& load the air-gapped ENTERPRISE licence grant\npython manage.py unlimited_seed|' \
      /app/backend/bin/docker-entrypoint-api-ee.sh \
 && grep -q "unlimited_seed" /app/backend/bin/docker-entrypoint-api-ee.sh

# --- UI stripping + RabbitMQ 4.x patches (last: most volatile layer) --------
COPY unlimited_strip_ui.py /tmp/unlimited_strip_ui.py
RUN python3 /tmp/unlimited_strip_ui.py
