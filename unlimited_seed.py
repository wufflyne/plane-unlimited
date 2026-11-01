"""
plane-unlimited: forge and load an air-gapped ENTERPRISE licence grant.

Django management command, installed as
    /app/backend/plane/license/management/commands/unlimited_seed.py
and appended to bin/docker-entrypoint-api-ee.sh after `manage.py startup`.

Runs on every API boot; idempotent and safe to run concurrently:
  1. waits for the Instance row (created by register_instance_ee; with
     IS_AIRGAPPED=1 that happens fully offline),
  2. fast-path: if a stored INSTANCE grant already verifies for the current
     instance_id with tier ENTERPRISE, skips re-forging,
  3. otherwise signs a new INSTANCE-scoped ENTERPRISE grant with the
     plane-unlimited Ed25519 key (whose public half replaced the shipped
     trust anchors) and verifies it through the real verify_grant(),
  4. upserts the license_grants row (token column widened to text once),
  5. syncs WorkspaceLicense rows (plan=ENTERPRISE, seats=1,000,000),
  6. disables instance telemetry.

Author: wufflyne <wufflyne@proton.me> — wufflyne.com
"""
import base64
import datetime
import json
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from plane.db.models import Workspace
from plane.ee.models.workspace import WorkspaceLicense
from plane.license.entitlements import resolve_entitlement
from plane.license.models import Instance
from plane.license.models.grant import LicenseGrant
from plane.license.trust.keys import load_trust_store
from plane.license.trust.verify import verify_grant, GrantScope
from plane.payment.flags.flag import FeatureFlag

KID = "plane-licence-prod-20261021"
SIGNING_KEY_PATH = "/app/backend/plane/unlimited_signing_key.pem"
LICENSE_KEY = "PLANE-UNLIMITED"
SEATS = 1_000_000
EXP = 4102444800  # 2100-01-01T00:00:00Z
EXP_DATE = datetime.datetime.fromtimestamp(EXP, tz=datetime.timezone.utc)
# How long to wait for the Instance row (first boot runs migrations first).
INSTANCE_WAIT_SECONDS = 120


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class Command(BaseCommand):
    help = "plane-unlimited: forge & load the air-gapped ENTERPRISE licence grant"

    def handle(self, *args, **options):
        # A single API runs this, but two boots may overlap during a restart
        # or an operator may run it by hand — serialize through Postgres.
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtext('plane_unlimited_seed'))")
        try:
            self._run()
        finally:
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtext('plane_unlimited_seed'))")

    def _run(self):
        instance = self._wait_for_instance()
        instance_id = str(instance.instance_id)

        grant = self._current_grant()

        # --- fast path: grant already valid for this instance ---------------
        if grant is not None:
            try:
                verified = verify_grant(
                    grant.token,
                    expected_scope=GrantScope.INSTANCE,
                    trust_store=load_trust_store(),
                    instance_id=instance_id,
                )
            except Exception:
                verified = None
            if (
                verified is not None
                and verified.tier == "ENTERPRISE"
                and grant.kid == KID
                and grant.expires_at >= EXP_DATE
            ):
                self.stdout.write(
                    "unlimited_seed: existing ENTERPRISE grant valid for this instance; keeping it"
                )
                self._sync_bookkeeping(instance)
                self.stdout.write(self.style.SUCCESS("unlimited_seed: ENTERPRISE grant active"))
                return

        token = self._forge_grant(instance_id)

        # --- widen license_grants.token to text if still varchar(255) -----
        # Only needed on volumes created by an older image; ALTER TABLE takes
        # an exclusive lock, so skip it entirely when already widened.
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT character_maximum_length FROM information_schema.columns
                WHERE table_name = 'license_grants' AND column_name = 'token'
                """
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                self.stdout.write("unlimited_seed: widening license_grants.token to text")
                cur.execute("ALTER TABLE license_grants ALTER COLUMN token TYPE text")

        # --- store / refresh the grant row ---------------------------------
        if grant is None:
            grant = LicenseGrant(workspace_id=None, scope="INSTANCE")
        grant.token = token
        grant.license_key = LICENSE_KEY
        grant.kid = KID
        grant.refusal_count = 0
        grant.expires_at = EXP_DATE
        grant.save()
        self.stdout.write("unlimited_seed: licence grant stored")

        self._sync_bookkeeping(instance)
        self.stdout.write(self.style.SUCCESS("unlimited_seed: ENTERPRISE grant active"))

    def _wait_for_instance(self) -> Instance:
        """Wait for the Instance row; register_instance_ee creates it at startup."""
        deadline = time.monotonic() + INSTANCE_WAIT_SECONDS
        while True:
            instance = Instance.objects.first()
            if instance is not None and instance.instance_id:
                return instance
            if time.monotonic() >= deadline:
                raise CommandError(
                    "unlimited_seed: no registered Instance after %ds — "
                    "instance registration (register_instance_ee) did not run; "
                    "check the `manage.py startup` output above"
                    % INSTANCE_WAIT_SECONDS
                )
            self.stdout.write("unlimited_seed: waiting for instance registration…")
            time.sleep(5)

    def _forge_grant(self, instance_id: str) -> str:
        try:
            with open(SIGNING_KEY_PATH, "rb") as fh:
                private_key = serialization.load_pem_private_key(fh.read(), password=None)
        except FileNotFoundError:
            raise CommandError(
                "unlimited_seed: signing key not found at %s — "
                "the image build must COPY unlimited_signing_key.pem" % SIGNING_KEY_PATH
            )
        if not isinstance(private_key, Ed25519PrivateKey):
            raise CommandError(
                "unlimited_seed: expected an Ed25519 signing key at %s "
                "(FIPS base images use ECDSA and need a different key)" % SIGNING_KEY_PATH
            )

        now = int(time.time())
        payload = {
            "iss": "prime.plane.so",
            "scp": "INSTANCE",
            "sub": {"instance_id": instance_id},
            "iat": now,
            "nbf": now,
            "exp": EXP,
            "period_end": EXP,
            "airgapped": True,
            "lic": LICENSE_KEY,
            "product": {"tier": "ENTERPRISE"},
            "limits": {"seats": SEATS},
            "entitlements": {flag.value: True for flag in FeatureFlag},
        }
        header = {"alg": "EdDSA", "typ": "plane-grant+jws", "kid": KID, "scp": "INSTANCE"}
        signing_input = (
            _b64url(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + _b64url(json.dumps(payload, separators=(",", ":")).encode())
        )
        token = signing_input + "." + _b64url(private_key.sign(signing_input.encode("ascii")))

        # Sanity-check with the real verifier before storing: if the trust
        # anchors were not swapped correctly this fails the boot loudly.
        grant = verify_grant(
            token,
            expected_scope=GrantScope.INSTANCE,
            trust_store=load_trust_store(),
            instance_id=instance_id,
        )
        if grant.tier != "ENTERPRISE" or grant.seats != SEATS:
            raise CommandError(
                "unlimited_seed: forged grant did not verify as ENTERPRISE/%d seats" % SEATS
            )
        return token

    def _current_grant(self) -> LicenseGrant | None:
        return LicenseGrant.objects.filter(
            workspace_id__isnull=True, scope="INSTANCE", deleted_at__isnull=True
        ).first()

    def _sync_bookkeeping(self, instance: Instance):
        """Workspace license rows, telemetry flag and the final proof output."""
        for ws in Workspace.objects.all():
            WorkspaceLicense.objects.update_or_create(
                workspace=ws,
                defaults={
                    "plan": "ENTERPRISE",
                    "purchased_seats": SEATS,
                    "is_paused": False,
                    "license_key": LICENSE_KEY,
                    "current_period_end_date": datetime.datetime(
                        2100, 1, 1, tzinfo=datetime.timezone.utc
                    ),
                    "last_verified_at": timezone.now(),
                },
            )
        self.stdout.write(
            "unlimited_seed: synced %d WorkspaceLicense rows" % Workspace.objects.count()
        )

        if instance.is_telemetry_enabled:
            instance.is_telemetry_enabled = False
            instance.save(update_fields=["is_telemetry_enabled"])
            self.stdout.write("unlimited_seed: instance telemetry disabled")

        for ws in Workspace.objects.all():
            ent = resolve_entitlement(str(ws.id))
            self.stdout.write(
                "unlimited_seed: workspace %s -> tier=%s seats=%s airgapped=%s"
                % (ws.slug, ent.tier, ent.seats, ent.airgapped)
            )
