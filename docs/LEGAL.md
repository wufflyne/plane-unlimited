# Licensing / legal notes

- The **base image** (`makeplane/plane-aio-commercial:stable`, v4.0.1) is
  Plane's closed-source *commercial* edition. This repository contains only a
  build-time patch set (key/trust-anchor swap, a Django management command
  installed next to Plane's own code, asset patches) — no Plane source code.
- Plane's open-source parts are AGPL-3.0; the commercial edition carries
  Plane's own commercial terms. Anyone redistributing this image or running it
  publicly should review Plane's licensing terms (plane.so) first.
- This project is intended for **private self-hosting**: an instance owner
  signs their own local ENTERPRISE grant with a key pair they control
  (optionally rotated via `scripts/generate-keys.sh`). It does not bypass any
  server-side licensing on Plane's side — the whole point is that the instance
  never talks to Plane's licensing servers at all.
