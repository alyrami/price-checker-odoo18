# Roadmap — alyrami_price_checker

> Note: This module was already mid-development when project docs were introduced.
> Per Rami's decision (2026-08-10), this file is NOT a retroactive history of all prior
> work — it starts tracking from the current approved feature forward. Do not backfill
> unrelated past changes into this file.

## Current Phase: Camera Barcode Scanning

Source: council-approved feature brief, two review rounds (general feature review +
focused Track B security review). All open questions from both rounds are resolved
and baked into the numbered requirements in `SPRINT_BACKLOG.md`.

Adds an in-browser camera barcode/QR scanner as an additional input method, split into
two independently-scoped tracks:

- **Track A — Inventory backend "Barcode Scanner"**: staff-only, additive-only, no
  access model change. Camera is just a new way to fill the existing barcode input.
- **Track B — POS "Price Checker" public kiosk**: brand-new unauthenticated
  self-service surface. Higher risk — new public route, new minimal-fields-only
  response function, new per-kiosk company scoping, new access-control surface
  (rate limiting + optional IP allowlist). See `SPRINT_BACKLOG.md` for the full
  security constraint list (B1-B13).

Status: **Done — implemented, code-reviewed (QC), functionally tested (QA), and confirmed
working via Rami's own on-device testing (2026-08-10).** See `SPRINT_BACKLOG.md` for the
full sequenced task list, the Task 16 security verification pass, and the on-device
testing log (including three bugs found and fixed after initial QA sign-off).

- **Track A (backend camera scanner):** confirmed working end-to-end on laptop webcam —
  opens, decodes, finds the correct product, existing lookup flow unchanged.
- **Track B (public kiosk):** confirmed working end-to-end on laptop webcam — no login
  prompt, camera scan and manual exact-match search both work, page confirmed to show
  only name/image/price (no stock data) even under direct inspection.
- **Outstanding:** mobile/phone camera testing has not happened yet — laptop webcam
  testing works over `http://localhost`, but real phone camera access needs HTTPS, so
  this is deferred until the module is on VPS staging (already HTTPS). Not a blocker for
  moving to git/deployment setup, but should be verified on staging before calling this
  fully done end-to-end.

## Later phases

Not yet scoped. Nothing beyond Camera Barcode Scanning is planned in this file today.
