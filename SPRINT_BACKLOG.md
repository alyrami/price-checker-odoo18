# Sprint Backlog — alyrami_price_checker

## Feature: Camera Barcode Scanning (Track A + Track B)

Source of truth for requirement numbers below: the finalized feature brief approved
2026-08-10, after two council-agent review rounds. Requirement IDs (A1-A6, B1-B13)
map directly to the brief's "Functional requirements" sections. Treat all of them as
settled — do not re-derive or renegotiate scope while implementing.

Legend: Status = Queued | In Progress | Blocked | Done | Returned (QA sent back)

---

### TASK 1 — Spike: check for reusable native camera scanner
**Status:** Done — decision recorded as the file-header comment in
`static/src/js/camera_barcode_scanner.js` (Task 2's output file), citing
`addons/point_of_sale/static/src/app/screens/product_screen/camera_barcode_scanner.js`
(POS-session-coupled, not reusable) and `addons/web/static/src/core/barcode/
barcode_video_scanner.js` (core's own BarcodeDetector-first/ZXing-fallback Owl
component — good technique reference, not reusable as-is for a bundle-free
public kiosk page). Decision: build a new framework-agnostic engine.
**Files touched:** none (read-only investigation of Odoo core `point_of_sale` addon
source — e.g. its `BarcodeVideoScanner` component and any related Settings toggle)
**Description:** Before writing new camera-capture code, check whether Odoo 18's
built-in POS camera scanner component/setting can be reused or adapted, or whether it's
too coupled to an authenticated POS session to reuse for either track. Document the
decision (reuse vs. build custom, and why) as a code comment at the top of Task 2's
output file — no separate report file.
**Acceptance criteria:** Decision is visible inline in Task 2's file header comment,
citing the exact Odoo source path if anything is reused.
**Constraint:** Investigation only, produces no runtime behavior change.

---

### TASK 2 — Shared camera capture/decode engine (framework-agnostic)
**Status:** Done — `static/src/js/camera_barcode_scanner.js` created. Implemented
as a plain classic script (not an `@odoo-module`, zero framework imports) so the
identical file can be shared by Track A's Owl dialog and Track B's bundle-free
kiosk page; registers itself on `window.AlyramiPriceChecker.CameraBarcodeScanner`.
**Files touched:** `static/src/js/camera_barcode_scanner.js` (NEW)
**Description:** One reusable, plain-JS module (no Owl/backend-framework dependency)
used by BOTH tracks: requests camera permission via `getUserMedia`, feature-detects
native `BarcodeDetector`, falls back to ZXing (Task 3) only when unavailable, runs a
decode loop against the live video feed, exposes `start(videoEl, {onDecode, onError,
onPermissionDenied})`, `stop()`, and `toggleTorch()` (best-effort, no-ops silently
where unsupported).
**Acceptance criteria:**
- `onDecode` fires once per code (debounced), never fires after `stop()`.
- Permission-denied / no-camera paths call `onPermissionDenied`/`onError`, never throw
  uncaught.
- Torch toggle is feature-detected (`MediaStreamTrack.getCapabilities().torch`), no-op
  and non-erroring when absent (iPhones, laptop webcams).
**Constraint (technical approach, brief):** BarcodeDetector-first, ZXing fallback
only, per the brief's approach section.

---

### TASK 3 — Bundle ZXing locally (no CDN)
**Status:** Done — vendored to `static/lib/zxing/zxing-library.js` (+ `LICENSE.txt`),
copied from Odoo 18 core's own vendored MIT-licensed copy. Implementation note /
deviation from the literal files-touched wording: it is NOT added to
`web.assets_backend`'s eager file list in `__manifest__.py` (a documented,
deliberate choice — see the manifest comment above the `assets` dict — because
adding it there would violate this task's own acceptance criteria of "not
loaded unconditionally on every page load"; Odoo core treats its equivalent
file the same way, present only in a test-only bundle). It is lazy-loaded on
demand, from its own static URL, by `camera_barcode_scanner.js`, only when
`BarcodeDetector` is unavailable.
**Files touched:** `static/lib/zxing/*` (or `static/src/js/vendor/zxing/*`, NEW —
vendored library files), `__manifest__.py` (register asset path in
`web.assets_backend`)
**Description:** Vendor the ZXing JS library into the module's own static assets.
Lazy-load it only when Task 2's feature detection determines `BarcodeDetector` is
unavailable.
**Acceptance criteria:** No `<script src="https://...">` or dynamic `import()`
pointing at any external/CDN host anywhere in the diff; not loaded unconditionally on
every page load.
**Constraint:** CONFIRMED DECISION in brief — bundled only, CDN loading is explicitly
disallowed (supply-chain risk on a logged-in session).

---

### TASK 4 — Shared camera scanner modal (Owl), with torch UI
**Status:** Done — `static/src/js/camera_scanner_dialog.js` and
`static/src/xml/camera_scanner_dialog.xml` created. Cancelable via footer
Cancel button, header close/back button, or ESC (all route through the same
dialog-service `close`, which always unmounts the component); `onWillUnmount`
always calls `engine.stop()` regardless of which path closed it. Torch button
uses `t-if` (fully absent, not disabled) until `onReady` reports
`torchSupported: true`.
**Files touched:** `static/src/js/camera_scanner_dialog.js` (NEW),
`static/src/xml/camera_scanner_dialog.xml` (NEW)
**Description:** Owl modal component (backend context only) wrapping Task 2's engine:
live preview, torch toggle button (rendered only when capability detected), close
button, calls a passed-in `onDecode` and auto-closes on success.
**Acceptance criteria:** Modal is cancelable without a scan; camera tracks are always
stopped on close/unmount (no camera indicator left on); torch button is fully absent
(not just disabled) when unsupported.
**Note:** Backend-only (`web.assets_backend`). Track B's public kiosk page (Tasks
11-13) talks to Task 2's engine directly and does NOT use this component, since the
kiosk page must not depend on the authenticated Odoo web client.

---

### TASK 5 — Track A: "Scan with Camera" button on backend Barcode Scanner
**Status:** Done — `static/src/js/barcode_scanner.js` and
`static/src/xml/barcode_scanner.xml` updated. Decode sets `state.barcode` and
calls the existing `searchProduct()` directly, no new lookup path.
`security/ir.model.access.csv` untouched by this task (confirmed).
**Files touched:** `static/src/js/barcode_scanner.js` (MODIFY),
`static/src/xml/barcode_scanner.xml` (MODIFY)
**Description:** Add a "Scan with Camera" button next to the existing barcode input.
Opens Task 4's modal. On decode: set `state.barcode`, close modal, call the existing
`searchProduct()` directly — same path the hardware scanner and manual Enter already
use. On permission denied/unsupported: notify via existing notification service,
leave manual input fully usable.
**Acceptance criteria (maps to A1-A6):**
- A1: button present next to existing input.
- A2: click opens live preview modal.
- A3/A4: decode auto-fills the same input field and triggers the existing
  `searchProduct()` lookup unchanged — no new lookup logic introduced.
- A5: denial/unsupported never blocks manual entry.
- A6: no access/security/model changes in this task — screen stays gated exactly as
  today (verify `security/ir.model.access.csv` untouched by this task).
**Constraint (gotcha):** decoded value must call `searchProduct()` directly, not go
through any name-search-style branching (this screen doesn't have one today — keep it
that way).

---

### TASK 6 — Track A manifest wiring
**Status:** Done — `__manifest__.py` `web.assets_backend` updated with
engine -> dialog -> barcode_scanner load order. `point_of_sale._assets_pos`
untouched.
**Files touched:** `__manifest__.py` (MODIFY — add Task 2/3/4 files to
`web.assets_backend`, correct load order: engine → ZXing (lazy) → dialog → 
barcode_scanner.js)
**Description:** Register all new Track A files in the backend asset bundle.
**Acceptance criteria:** Module installs/updates cleanly; backend Barcode Scanner
screen loads with no console errors; nothing from this task touches
`point_of_sale._assets_pos` (Track A does not touch POS).

**— Track A is shippable independently after Task 6. —**

---

### TASK 7 — Kiosk device config model + access rules
**Status:** Done — `models/price_checker_kiosk.py` created (new model, no
`default=` on `company_id`, `required=True`), `models/__init__.py` updated,
`security/price_checker_security.xml` created (new `group_kiosk_admin`
standalone group + new `Price Checker` module category + a multi-company
`ir.rule`, per Rami's resolved decision below), `security/ir.model.access.csv`
updated with one new row granting `group_kiosk_admin` full CRUD and nothing
else. No other group (including `stock.group_stock_manager`/
`stock.group_stock_user`) has any row for this model; public/portal users get
zero access.
**Files touched:** `models/price_checker_kiosk.py` (NEW), `models/__init__.py`
(MODIFY), `security/ir.model.access.csv` (MODIFY), `security/price_checker_security.xml`
(NEW — new group definition)
**Description:** New model `price_checker.kiosk`, one record per physical
tablet/kiosk device:
- `name` (Char, required)
- `token` (Char, required, unique, indexed, unguessable — default a UUID — used in
  the public URL path)
- `company_id` (Many2one `res.company`, **required, NO default value**)
- `active` (Boolean, default True)
- `rate_limit_per_minute` (Integer, default 25)
- `allowed_ip_cidr` (Char, optional — e.g. `192.168.1.0/24`)

**Acceptance criteria (maps to B7):** `company_id` has no default and is required —
creating a kiosk record without explicitly setting a company must fail validation, not
silently fall back to `env.company` or "first company." Public/portal users get zero
access to this model.

**RESOLVED (2026-08-10) — access-scoping decision from Rami:** Do NOT reuse
`stock.group_stock_manager` or System Administrator. Create a new, dedicated security
group `group_kiosk_admin` (defined in new `security/price_checker_security.xml`),
scoped to exactly the `price_checker.kiosk` model with full CRUD and nothing else —
no inherited access from any existing role. Membership is assigned manually per
person by an admin (not auto-granted to any existing group), so no `implied_ids`
chain from `stock.group_stock_manager` or similar. `ir.model.access.csv` gets a new
row granting `group_kiosk_admin` full CRUD on `price_checker.kiosk`; no other group
(including `stock.group_stock_manager`/`stock.group_stock_user`) gets any access to
this model. This decision unblocks Tasks 8, 9, and 12.

---

### TASK 8 — Kiosk admin UI (backend)
**Status:** Done — `views/price_checker_kiosk_views.xml` created (list + form;
`token` read-only with a header "Regenerate Token" button/confirm dialog
calling `action_regenerate_token()`; `kiosk_url` computed field with
`CopyClipboardURL` widget). `views/price_checker_menu.xml` updated with a new
"Kiosk Devices" menu item gated with `groups="group_kiosk_admin"`.
**Files touched:** `views/price_checker_kiosk_views.xml` (NEW),
`views/price_checker_menu.xml` (MODIFY)
**Description:** List/form view for staff to manage kiosk records — name, token
(read-only after creation, with an explicit "Regenerate" action rather than being
freely editable, since it's effectively a secret controlling which store's kiosk a URL
reaches), company_id, active, rate_limit_per_minute, allowed_ip_cidr, plus a computed
read-only field showing the full public kiosk URL for easy copy-paste onto a tablet.
New menu item under the existing "Price Checker" backend menu, gated to the group
confirmed in Task 7.
**Acceptance criteria:** token not directly editable in the form; URL is easy to copy
for setup.

---

### TASK 9 — Track B: minimal-fields serializer + public lookup route (core)
**Status:** Done — `controllers/price_checker_controller.py` extended, purely
additive, appended after `_serialize_product`. New
`_serialize_public_product()` returns exactly `name`/`image_128`/`price`/
`currency`. New route `/price_checker/kiosk/<token>/lookup`
(`auth='public'`, `type='json'`, POST): resolves kiosk by token via
`_get_active_kiosk()`, company scoped strictly from `kiosk.company_id`, exact
`('barcode','=', ...)` match only, calls `_serialize_public_product()` only.
`search_by_barcode`/`get_product`/`search_by_name`/`_serialize_product`
verified byte-for-byte unchanged (see Task 16 below).
**Files touched:** `controllers/price_checker_controller.py` (MODIFY — additive only,
do not touch `search_by_barcode`, `get_product`, `search_by_name`, or
`_serialize_product`)
**Description:** Add a brand-new `_serialize_public_product(product)` method
returning ONLY: `name`, `image_128` (thumbnail), `price` + `currency` (using the same
sales-tax-only calculation already in use, but nothing else in the dict). Add new
route `/price_checker/kiosk/<string:token>/lookup`, `auth='public'`,
`methods=['POST']`, read-only:
1. Look up kiosk by token; 404/generic error if missing or `active=False`.
2. Resolve company strictly from `kiosk.company_id` — never from
   request/session/`env.company`, never a "first company" fallback.
3. Accept `barcode` param, EXACT match only (`('barcode', '=', barcode.strip())`)
   against `product.product` then `product.template`, scoped to the kiosk's company —
   no `ilike`, no name search, no fallback to any name-search logic.
4. Call `_serialize_public_product()` — never `_serialize_product()`.

**Acceptance criteria (maps to B1, B2, B3, B7 dependency, B10, B11, B12, B13):**
- Response dict literal contains only name/image/price/currency — no
  `qty_available`, `stock_status`, `default_code`, `categ_id`/`categ_name`,
  `standard_price`, `barcode` echo, or anything else. Verify by reading the code, not
  just the rendered screen (B10, B3 — "assume a hostile user will poke at it
  directly").
- Zero `.write(`, `.create(`, `.unlink(` calls anywhere in this new code path (B13).
- Query is exact-match only, no `ilike`, no free-text fallback (B12).
- `company_id` used in the search domain comes only from the resolved kiosk record,
  never any other source (B7 dependency).
- Diff shows only additions — `search_by_barcode`, `get_product`, `search_by_name`,
  `_serialize_product` are byte-for-byte unchanged (B11).

---

### TASK 10 — Track B: rate limiting on the public lookup route
**Status:** Done — `_kiosk_rate_limited()` added to
`controllers/price_checker_controller.py`: in-memory sliding-window counter
keyed by `(kiosk.token, requester IP)`, default 25/min (from the model field),
per-kiosk (not global). Over-limit -> `{'error': 'Too many requests...',
'product': None}`, HTTP 200 (never a 500), logged at `_logger.warning`. The
in-memory/single-worker limitation is documented inline at the top of the
controller file. `models/price_checker_kiosk.py` was NOT modified for this
task — counters are not tracked on the model.
**Files touched:** `controllers/price_checker_controller.py` (MODIFY — extends Task 9's
route), `models/price_checker_kiosk.py` (MODIFY, only if counters are tracked on the
model)
**Description:** Throttle Task 9's route keyed by kiosk token (+ requester IP as
secondary key), enforcing `kiosk.rate_limit_per_minute` (default 25, per B9's
"~20-30/min" guidance). Over-limit requests return a generic non-500 error, no product
data, logged at warning level.
**Acceptance criteria (maps to B4, B9):** default lands in 20-30/min range; limit is
per-kiosk, not global (one busy store doesn't throttle another); an over-limit
response never contains product data.
**Constraint:** document any known limitation inline (e.g., in-memory counters don't
survive a restart or share state across multiple worker processes) — the brief only
asks for "a sane conservative default," not perfect distributed rate limiting.

---

### TASK 11 — Track B: local-network IP allowlist (defense in depth)
**Status:** Done — `_kiosk_ip_allowed()` added to
`controllers/price_checker_controller.py`, checked in both `kiosk_lookup`
(Task 9's route) and `kiosk_page` (Task 12's route). Blank `allowed_ip_cidr`
skips the check entirely. Mismatch -> generic `request.not_found()` /
`{'error': 'Not found', ...}`, same shape as an unknown token, logged at
warning level — no stack trace, no confirmation the kiosk exists. Uses
`request.httprequest.remote_addr` (relies on Odoo `--proxy-mode` + ProxyFix
for the true client IP behind a reverse proxy — flagged as a manual-test note
below).
**Files touched:** `controllers/price_checker_controller.py` (MODIFY — extends Task
9's route and Task 12's page route)
**Description:** If `kiosk.allowed_ip_cidr` is set, reject requests from outside that
CIDR (both the lookup route and the page route). Blank = skip check (opt-in per
store).
**Acceptance criteria (maps to B8):** configured-and-mismatched → generic error, no
stack trace, no confirmation the kiosk exists; blank → unchanged behavior. Framed as
one extra layer, not the sole control (rate limiting + exact-match/minimal-fields
remain primary, consistent with the brief's "where feasible").

---

### TASK 12 — Track B: public kiosk page route + template shell
**Status:** Done — `kiosk_page()` route added to
`controllers/price_checker_controller.py`
(`/price_checker/kiosk/<token>`, `type='http'`, `auth='public'`). New
`views/price_checker_kiosk_public_templates.xml` — fully standalone HTML
document (no `web.layout`/`web.frontend_layout` inheritance, no session
bootstrap script, no company-logo route), loads only
`alyrami_price_checker.assets_kiosk` (Task 14). Manual barcode input + submit
button, "Scan with Camera" button, result area limited to name/image/price
markup only. Verified (see Task 16) that no stock/cart/POS-session data or
markup exists anywhere in the template.
**Files touched:** `controllers/price_checker_controller.py` (MODIFY — add
page-serving route), `views/price_checker_kiosk_public_templates.xml` (NEW, QWeb page
template)
**Description:** Route `/price_checker/kiosk/<string:token>`, `type='http'`,
`auth='public'`. Resolve kiosk by token (same not-found/inactive handling as Task 9).
Render a minimal, self-contained public page — no Odoo backend menu bar, no login
prompt, no dependency on any authenticated or POS session. Shell includes: manual
barcode entry input + submit button, "Scan with Camera" button, result area
(name/image/price only).
**Acceptance criteria (maps to B1, B6):** page fully usable with zero authentication;
manual entry field works independently of camera availability (B6); rendered HTML
contains no markup or data referencing stock, cart, or POS-session state anywhere —
check page source, not just what's visually displayed (B3).

---

### TASK 13 — Track B: kiosk JS (camera scan + manual exact-match entry)
**Status:** Done — `static/src/js/kiosk_price_checker.js` created. Plain
classic script (not an `@odoo-module`), reads Task 2's engine off
`window.AlyramiPriceChecker.CameraBarcodeScanner`. Both manual submit and
camera decode call the single `lookupBarcode()` function, which is the only
code path that calls the server (Task 9's `/price_checker/kiosk/<token>/lookup`
route). No `search_by_name`-style branching or route anywhere in this file.
Renders only `name`/`image_128`/`price`+`currency` from the response.
**Files touched:** `static/src/js/kiosk_price_checker.js` (NEW)
**Description:** Vanilla-JS controller for Task 12's page. Imports Task 2's shared
engine directly (not Task 4's Owl dialog — backend-only). Manual submit and camera
decode both call Task 9's lookup route through the exact same single code path — no
client-side "looks like a name vs. a barcode" branching of any kind, since there is no
name-search route on this surface to fall back to. Renders only name/image/price from
the response. Camera denied/unsupported → manual field stays usable.
**Acceptance criteria (maps to B5, B6, B12, and the brief's ">20 chars / no digits"
gotcha note):** decoded and manually-typed barcodes both go through one identical
request path to Task 9's route; nothing in this file calls
`/web/price_checker/search_by_name` or anything name-search-like; template/rendering
references only name, image, price+currency.

---

### TASK 14 — Track B: kiosk CSS + isolated manifest bundle
**Status:** Done — `static/src/css/kiosk_price_checker.css` created. New
`alyrami_price_checker.assets_kiosk` bundle added to `__manifest__.py`,
containing the shared engine (Task 2) + kiosk JS (Task 13/15) + kiosk CSS
(Task 14); referenced only from Task 12's template via `t-call-assets`. Not
added to `web.assets_backend`, `point_of_sale._assets_pos`, or any other
bundle. ZXing remains lazy-loaded on demand (same reasoning as Task 3), not
eagerly listed in this bundle either. Task 1-6's `web.assets_backend` entries
were not touched by this task.
**Files touched:** `static/src/css/kiosk_price_checker.css` (NEW), `__manifest__.py`
(MODIFY — new dedicated bundle, e.g. `alyrami_price_checker.assets_kiosk`, containing
Task 2/3's shared engine + ZXing vendor files + Task 13/14's JS/CSS, referenced only
from Task 12's template)
**Description:** Give the public kiosk page its own isolated asset bundle — must NOT
be added to `web.assets_backend` or any authenticated/POS bundle.
**Acceptance criteria:** kiosk page network requests show only kiosk-scoped assets;
diff touches only new manifest entries — Tasks 1-6's `web.assets_backend` entries are
unchanged.

---

### TASK 15 — Track B: torch toggle on kiosk page (cross-track item, best-effort)
**Status:** Done — implemented directly inside `static/src/js/kiosk_price_checker.js`
(Task 13's file, built together for coherence since both land in the same
review) and `views/price_checker_kiosk_public_templates.xml`. Torch button
starts hidden (`pc-kiosk-hidden` class) and is only unhidden when the camera
engine's `onReady` callback reports `torchSupported: true`; stays hidden
otherwise (iPhone Safari, desktop webcams) with no error.
**Files touched:** `static/src/js/kiosk_price_checker.js` (MODIFY), Task 12's
template (MODIFY)
**Description:** Same torch behavior as Task 4, via Task 2's engine directly, surfaced
as a button that's hidden entirely when unsupported.
**Acceptance criteria:** no error on iPhone Safari or desktop webcams (button just
doesn't render); not a v1 blocker if flaky on a given Android device (brief marks this
best-effort/recommended, not required).

---

### TASK 16 — Security verification pass (Track B, pre-QA)
**Status:** Done — walked the landed diff against every B-requirement referenced
across Tasks 7-15, plus the 6 explicit hard Track B constraints, by re-reading
the actual code (not the rendered page). Results below; anything that would
have failed was to be routed back to its owning task rather than patched here
— nothing failed.

**Explicit Track B hard constraints (from the task brief):**
1. New public route's response function returns ONLY name/image/price+currency,
   even to a direct/malformed request — **PASS**. `_serialize_public_product()`
   (controllers/price_checker_controller.py) has exactly one `return` statement,
   a 4-key dict literal (`name`, `image_128`, `price`, `currency`), no
   conditional branch that adds more keys, and no `except` fallback with a
   wider dict (unlike the staff-facing `_serialize_product`, this one has no
   safety-net fallback at all — an exception here is caught by
   `kiosk_lookup`'s outer `try/except`, which returns the same generic
   `{'error': 'Server error', 'product': None}` regardless of cause).
   Confirmed the *only* two possible shapes of the `product` key across every
   code path in `kiosk_lookup` are `None` or that exact 4-key dict.
2. `search_by_barcode`, `get_product`, `search_by_name`, `_serialize_product`
   remain byte-for-byte unchanged — **PASS**. Re-read the full file: Track B
   code was appended after `_serialize_product`'s closing brace; the only
   change above that point is two new `import` lines and one new module-level
   rate-limit-state block, both before the class definition, not inside any
   of those four methods.
3. `company_id` for a public kiosk request comes only from the resolved kiosk
   record — **PASS**. Grepped the whole file: `request.env.company` /
   `env.company` appears only inside the pre-existing `_company_domain()` and
   `_get_company_stock_qty()`, both exclusively used by the staff-facing
   routes. Every Track B method that needs a company reads `kiosk.company_id`
   only, and `kiosk` is always the return of `_get_active_kiosk(token)`.
4. Manual entry on the kiosk page is exact-barcode-match only, no name-search
   fallback — **PASS**. `_kiosk_product_lookup()` uses `('barcode', '=',
   barcode)` only; grepped the file for `ilike` — the only three matches are
   in the pre-existing `search_by_name` (untouched, staff-only). Grepped
   `kiosk_price_checker.js` for `search_by_name`/`search_by_barcode`/
   `get_product` — no matches outside a comment.
5. Zero write/create/unlink ORM calls anywhere in the new public controller
   code — **PASS**. Grepped the entire controller file for `.write(`,
   `.create(`, `.unlink(` — the only match in the whole file is inside a
   comment (line documenting this very rule). Every Track B DB access is a
   `.search(` call.
6. ZXing vendored into the module's own static assets, never CDN — **PASS**.
   `static/lib/zxing/zxing-library.js` is a local file inside this module;
   `camera_barcode_scanner.js`'s `ZXING_LIB_URL` constant is a same-origin,
   module-relative path (`/alyrami_price_checker/static/lib/zxing/...`).
   Grepped all new JS/XML for `http://`/`https://`/`cdn` — no matches.

**B1-B13 (as referenced by task annotations throughout this file):**
- B1 (public page usable with zero auth; response is name/image/price/currency
  only) — **PASS**. `kiosk_page`/`kiosk_lookup` are both `auth='public'`; no
  redirect to `/web/login` anywhere; response shape covered under constraint 1
  above.
- B2 (minimal-fields serializer is the only thing ever returned publicly) —
  **PASS**. See constraint 1.
- B3 ("assume a hostile user will poke at it directly"; no stock/cart/POS
  markup on the page) — **PASS**. `kiosk_lookup`/`kiosk_page` apply identical
  checks (kiosk resolution, IP allowlist, rate limit) regardless of whether
  the request came from `kiosk_price_checker.js` or a direct curl/script call
  — there is no UI-side gate the server trusts. Re-read
  `price_checker_kiosk_public_templates.xml` end to end: no field, variable,
  or comment referencing stock/qty/cart/POS/session state anywhere.
- B4 (rate limiting exists on the public route) — **PASS**. `_kiosk_rate_limited()`
  called before any product data is fetched in `kiosk_lookup`.
- B5 (kiosk JS: single request path, no branching) — **PASS**. `lookupBarcode()`
  is the only function that calls the server; both the form submit handler and
  the camera `onDecode` callback call it directly with the raw string.
- B6 (manual entry works independently of camera) — **PASS**. The form/input
  are never disabled by any camera code path; `openCamera()`'s
  `onPermissionDenied`/`onError` handlers only post a message and close the
  camera panel — they never touch `input.disabled` or the form.
- B7 (company_id only from kiosk record, required, no default) — **PASS**.
  `models/price_checker_kiosk.py`: `company_id = fields.Many2one('res.company',
  required=True, ...)` — no `default=` kwarg present. Controller-side: see
  constraint 3.
- B8 (IP-allowlist mismatch and unknown/inactive token both return a generic,
  non-confirming error) — **PASS**. `kiosk_lookup` returns the identical
  `{'error': 'Not found', 'product': None}` shape for "no such token",
  "inactive kiosk", and "IP not allowed"; `kiosk_page` returns
  `request.not_found()` (a generic 404) for all three. No response includes a
  traceback or distinguishing message.
- B9 (rate limit default in the ~20-30/min range) — **PASS**. Model default
  `rate_limit_per_minute = 25`.
- B10 (verify by reading code, not just the rendered screen) — **PASS**. This
  entire task was performed by reading `controllers/price_checker_controller.py`,
  `models/price_checker_kiosk.py`, the new views, and the new JS directly, not
  by exercising the UI (camera/browser testing isn't available to this agent
  regardless — see manual test notes below).
- B11 (Track A's screen and the three original POS routes unchanged except
  Task 5's additive button) — **PASS**. See constraint 2 for the controller;
  `static/src/js/pos_price_checker.js`, `static/src/xml/pos_price_checker.xml`,
  and `static/src/css/pos_price_checker.css` were not touched by any task in
  this sprint (not in any files-touched list, not edited).
- B12 (exact-match only, no ilike, no fallback) — **PASS**. See constraint 4.
- B13 (zero write/create/unlink in new controller code) — **PASS**. See
  constraint 5.

No requirement failed this pass. Nothing was routed back to an earlier task.
**Files touched:** none new — review only, across `controllers/price_checker_controller.py`,
`models/price_checker_kiosk.py`, `security/ir.model.access.csv`, and the new views/JS
from Tasks 7-15
**Description:** Walk the full B1-B13 requirement list against the actual landed diff
before handing off to qc-agent/qa-agent, specifically confirming:
- The new public route(s) cannot reach `_serialize_product`, `qty_available`, or
  `stock_status` under any input, including malformed/direct requests that bypass the
  UI entirely (B3, B10).
- No write/create/unlink ORM calls exist anywhere in the new controller code (B13).
- `company_id` is never inferred or defaulted anywhere in the new code — only ever
  resolved from the kiosk token (B7).
- Track A's backend screen and the existing POS cashier Price Checker screen (and its
  three original routes: `search_by_barcode`, `get_product`, `search_by_name`) are
  unchanged except for Task 5's additive camera button (B11).
**Acceptance criteria:** explicit pass/fail note against each of B1-B13. Anything that
fails routes back to the specific earlier task responsible — not silently patched
here.

---

## Known deployment hazard (found during Rami's on-device testing, 2026-08-10) — CONFIRMED ROOT CAUSE, RESOLVED

During manual retesting after Tasks 1-16 landed, Rami's admin account repeatedly lost Point of
Sale, Inventory, and Invoicing Administrator access (dropped to a ~12-group baseline). This was
investigated in stages; an early theory (a stale Settings > Users browser tab saving over a
newly-added permission category) was tested and ruled out — a controlled isolation test with
every browser tab closed still showed the account was, at that point, genuinely intact, and a
later occurrence reproduced with no browser tab involved at all. The stale-tab theory only
explained part of the timeline; the actual mechanism, confirmed by reading Odoo's own source, was
found afterward:

**Confirmed root cause — unrelated to this module's code:** Rami's personal server launcher
script (`odoo18 -rami.bat`, outside this repo) ran `python odoo-bin ... -i base` on every
startup. `odoo/tools/convert.py` (Odoo core): `noupdate="1"` protection on a data record is
skipped entirely whenever the owning module is loaded in **install** mode (`-i`), not just
**update** mode. Odoo core's own `odoo/addons/base/data/res_users_data.xml` defines the `admin`
user (xmlid `base.user_admin`) with `<field name="groups_id" eval="[Command.set([])]"/>` inside a
`noupdate="1"` block — normally applied only once, at first database creation. Because `-i base`
bypassed that protection on every launch, this reset `admin`'s groups to empty on every startup,
immediately followed by `base/security/base_groups.xml`'s (correctly unprotected) baseline grants
re-adding only a small fixed set — never the app-level Administrator groups. This affected `admin`
specifically (and only `admin`) because only `admin` carries the `base.user_admin` xmlid; a
manually-created user has no such data-file record and is structurally immune. Confirmed via a
live, read-only isolation test comparing `admin` vs. a throwaway `test` user's full group lists
across a real restart.

**Fix:** removed `-i base` from `odoo18 -rami.bat` (Rami's personal script, not part of this
module). No code or data in this module was changed for this issue, and none was needed.

**Safe procedure going forward:** don't run `-i <module>` against an already-installed database
for routine startups — it forces Odoo to bypass `noupdate` protection for that module's entire
data set, not just the module being worked on. This applies to any Odoo instance, not just this
one.

## On-device testing results (Rami, 2026-08-10) — both tracks confirmed working

Full functional retest on real hardware (laptop webcam), after QC/QA sign-off surfaced further
issues that only appeared under actual browser/camera conditions QA's environment couldn't
exercise. Three real bugs were found and fixed during this pass — documented here since they
weren't caught by the earlier QC/QA review:

1. **Camera opened but never decoded (ZXing path only — desktop Chrome, no native
   `BarcodeDetector`).** Root cause: the `<video>` elements in both `camera_scanner_dialog.xml`
   (Track A) and `price_checker_kiosk_public_templates.xml` (Track B) had an `autoplay="autoplay"`
   HTML attribute. The browser auto-played the stream the instant it attached, which raced
   ZXing's own internal play-on-load handshake — ZXing's `playVideoOnLoad()` waits for a
   `"playing"` event that had already fired before ZXing attached its listener, so its decode
   loop (`decodeContinuously()`) was never reached. Fixed by removing `autoplay` from both
   templates; `camera_barcode_scanner.js` is now the only thing that ever calls `.play()` on
   these elements.
2. **Track B kiosk page: neither manual search nor camera scan did anything; console showed
   `Uncaught ReferenceError: odoo is not defined`.** Root cause: Odoo's asset bundler wraps every
   JS file passed through `t-call-assets` in an `odoo.define(...)` call, regardless of the
   `/** @odoo-module **/` tag — and the kiosk page deliberately never loads Odoo's module loader
   (by design, so it has zero web-client dependency), so `odoo.define` didn't exist and the very
   first line of the bundle threw, silently killing both files. Fixed by no longer routing
   `camera_barcode_scanner.js`/`kiosk_price_checker.js` through `t-call-assets` — they're now
   served as plain `<script src="...">` tags pointing at the raw static files, which Odoo serves
   unmodified. `alyrami_price_checker.assets_kiosk` in `__manifest__.py` now only contains the
   CSS file.
3. **The `-i base` permissions landmine** — see the "Known deployment hazard" section above.
   Unrelated to this module's code; fixed in Rami's personal launcher script, not this repo.

**Confirmed working (laptop webcam):**
- Track A: camera opens, decodes a real barcode (`7622100966500`), finds the correct product,
  existing lookup flow unchanged.
- Track B: no login prompt, camera scan works, manual exact-match search works, page confirmed
  (by direct inspection, not just visually) to show only name/image/price — no stock data
  anywhere.

**Outstanding — not yet tested:** real phone camera access. `getUserMedia` requires HTTPS or
`localhost`; Rami's local setup can't serve a phone over either, so mobile testing is deferred
until this module is on VPS staging (already HTTPS). Not a blocker for git/deployment setup, but
should happen on staging before this is considered fully verified end-to-end.

## Out of scope (per brief — do not implement)
- No changes to pricing logic, tax-inclusive calculation, or POS integration
  behavior.
- No changes to physical barcode reader support.
- No cart, checkout, or order creation on Track B's public kiosk.

## Accepted risk (per brief — not a defect to "fix")
A public kiosk can in principle be scripted to walk the barcode space and enumerate
the price list. Rate limiting (Task 10) slows this, does not prevent it. This is an
accepted tradeoff, not something later tasks should try to close off further without
Rami's sign-off.
