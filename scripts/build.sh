#!/usr/bin/env bash
# plane-unlimited: build the patched image locally (install path B).
#
# Usage:  scripts/build.sh [tag]     (default tag: plane-unlimited:local)
# Author: wufflyne <wufflyne@proton.me> — wufflyne.com
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:-plane-unlimited:local}"
docker build -t "$TAG" .
echo
echo "Built $TAG"
echo "To use it: set PLANE_IMAGE=$TAG in .env, then: docker compose up -d"
