#!/usr/bin/env bash
# plane-unlimited: generate / rotate the Ed25519 licence-signing key pair.
#
# The private key signs the INSTANCE-scoped ENTERPRISE grant that
# unlimited_seed forges on every boot; its public half is installed into the
# image as the licence trust anchors (keys/). Rotating means regenerating
# both — they must stay a matching pair.
#
# Usage:  scripts/generate-keys.sh
# Author: wufflyne <wufflyne@proton.me> — wufflyne.com
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - <<'EOF'
import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

key = Ed25519PrivateKey.generate()
pem = key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
pub = key.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
)

with open("unlimited_signing_key.pem", "wb") as fh:
    fh.write(pem)
os.chmod("unlimited_signing_key.pem", 0o644)

# Two trust-anchor files (kid = filename stem; both kept consistent so the
# verifier finds the key under either anchor Plane looks up).
for name in ("plane-licence-prod-20261021", "plane-licence-prod-202610"):
    with open(os.path.join("keys", name + ".pem"), "wb") as fh:
        fh.write(pub)
print("plane-unlimited: new key pair written (unlimited_signing_key.pem + keys/)")
print("plane-unlimited: rebuild the image for it to take effect")
EOF
