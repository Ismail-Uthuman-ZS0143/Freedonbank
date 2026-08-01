# Credit File Server 2.0 — Freedom Bank of Virginia

## What this is
`FBOV_Document_Request_Flow_Mock_v3.html` (current) is a static, no-backend
UI mockup (Intics for Freedom Bank of Virginia) — a commercial-loan document
request flow: banker login → request → customize checklist → secure email →
customer upload → parking-bay review → twin extraction → credit report →
term sheet & commitment → HITL verification/handoff → activity log.
`FBOV_Document_Request_Flow_Mock_v2.html` is the prior version, kept for
history -- Steps 1-6 were rebuilt against v3 once it was provided; v3 also
adds two new macro-steps (Credit report, Term sheet & commitment) and
renumbers everything after them, which hasn't been reconciled into this
project's Step 7+ numbering yet (see the "Step numbering" note below).
Prepared by Intics (A Zuci Company) as a design concept, pure HTML/CSS, no
JS logic.

## Current goal
Build a real, working version, one mockup step at a time. Steps 1-7 done
(1-6 rebuilt against v3, see "Step 2b" below); next up is Step 8 (extraction
review & handoff + business twin details) -- reconcile v3's step numbering
first (see "Step numbering" note).

- Frontend: Next.js + React + TypeScript (matches `extract-lab` and the
  user's default stack). Dev server on port 3005.
- Backend: Django + DRF + Postgres — same tool/architecture as the sibling
  `appstore` project (`backend/config`, per-feature Django apps, DRF
  `@api_view` functions, session auth via `CsrfExemptSessionAuthentication`).
  Dev server on port 8001, proxied through Next's rewrite (see
  `next.config.mjs`) so the browser only ever talks to port 3005.
- Full test-case spec (built + planned) lives in `TEST_CASES.md` — check it
  before adding a new step so cases aren't duplicated or missed.

## Database decision — IMPORTANT
Do **not** use the existing `inticsdev` Postgres database for this project.
It's real Intics platform infrastructure — 88 schemas including
`user_management`, `session`, `extraction`, `audit`, etc. — not a scratch
DB. Confirmed with the user; this project gets its own database.

- Target database name: **`fbv`**
- Owner: `ismail` (OS/Postgres role already exists, peer auth works)
- Postgres 17, running locally on port 5432 (`pg_lsclusters` confirms a
  single cluster — no multi-instance ambiguity)

## Blocker — RESOLVED
`ismail` now has `rolcreatedb = t` (fixed via `sudo -u postgres psql -c
"ALTER ROLE ismail CREATEDB;"` run properly in a real terminal). Database
`fbv` has been created (`createdb -O ismail fbv`) and is reachable:
`psql -d fbv` connects fine, owned by `ismail`.

## Step 1 — Banker sign-in — done
`backend/accounts` app: Django's built-in `User` (login by email, stored as
`username`), `LoginEvent` audit model (append-only -- no add/change
permission in admin, matches "every sign-in audited"). Endpoints:
`POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`.
`app/page.tsx` is the real sign-in screen (navy/gold palette, split panel,
MFA notice -- MFA/SSO are copy-only placeholders, not implemented). A test
banker exists: `d.whitfield@freedombankva.com` / `Freedom2026!`.
17 tests in `backend/accounts/tests.py`.

## Step 2 — Dashboard: create & send request — done (minus Steps 3-4 deps)
`backend/document_requests` app: `DocumentRequest` model (borrower/phone/
email/company, status draft→sent→uploads_complete/expired, `link_token` +
7-day `link_expires_at`). Endpoints: `POST /api/requests/validate` (live
per-field checks), `GET/POST /api/requests` (list+metrics / create),
`POST /api/requests/<id>/resend`. `app/dashboard/page.tsx` is the real
screen (metrics tiles, new-request form with onBlur validation, recent
requests list with Resend). 24 tests in `backend/document_requests/tests.py`.

**Deliberately not faked:** the mockup claims "domain verified" / "deliverable
email" and "matches state registry" -- no real mail-verification or business
registry API exists, so validation is honestly scoped to format checks only,
with wording that doesn't overclaim. Also: `docsInParkingBay` and
`sessionsEndedFraud` metrics are `null` (not a fake `0`) since they depend on
Step 4, which isn't built.

**Gotcha worth remembering:** Next.js strips a trailing slash on `/api/...`
paths *before* its rewrite proxy runs, so a Django route that only exists at
the slash form silently breaks (redirect loop, not an error). Fixed by giving
`document_requests`'s list/create endpoint an exact no-slash route directly
in `config/urls.py`. Watch for this on every new endpoint.

**Also worth remembering:** gunicorn renames its process title after start
(`gunicorn: master [config.wsgi:application]`), so `pkill -f "gunicorn
config.wsgi:application --bind ..."` never matches a *running* instance --
only kills it if caught during the brief startup window. Kill by PID (from
`ss -ltnp` or `ps aux | grep gunicorn`) instead when restarting after a code
change.

## Step 2b — Customize & send secure upload link — done (v3 rebuild)
When v3 of the mockup arrived it replaced Step 2's fixed 5-item checklist
with a real ~50-item master template across 8 categories, each tagged
**Lender** (customer-facing) or **Loan Admin** (internal-only) -- so this
whole area got rebuilt, cascading through Steps 3-6. Two scope questions
were asked and answered before building:

1. Should Loan Admin items get real tracking or stay UI-only? **Real
   tracking, no upload mechanism yet** -- they're genuine `ChecklistItem`
   rows (visible banker-side), permanently `status='pending'` since there's
   no upload path for them, an explicit documented gap. All
   completion/review/metrics logic is defined purely in terms of Lender
   items so this never blocks anything.
2. Build custom item add/remove too, or just the fixed template with
   checkboxes? **Fixed template + checkboxes only** -- custom items (shown
   in the mockup's "+ Add item" row) aren't built.

What got built: `checklist.py`'s `CHECKLIST_TEMPLATE` (the full master list,
transcribed item-for-item from the v3 mockup's modal, including its exact
default-selected state -- verified against the mockup's own "12
customer-facing · 16 internal" count). `ChecklistItem` gained
`category`/`audience` fields (migration `0008`). New `GET
/api/requests/checklist-template` endpoint; `POST /api/requests` gained an
optional `selectedItems: [{category, name}]` field -- **the server resolves
audience from the template, never trusts a client-supplied value**, and
400s on an unknown item. Omitting `selectedItems` falls back to the
template's default selection, so every pre-existing "send" test/flow kept
working unchanged -- no ripple-breakage across the other ~130 existing
tests. `email_service.py`, `upload_info_view`, `upload_document_view`, the
Step 6 `_review_state` gate, and the dashboard/parking-bay metrics were all
updated to filter to Lender items only (Loan Admin items never shown to the
customer, never block completion or review-completeness). 27 new tests
(`ChecklistTemplateTests`, `ChecklistSelectionAtSendTests`,
`LenderLoanAdminSplitTests`), 153 total across the whole backend.

Frontend: `app/dashboard/page.tsx` gained a `CustomizeModal` (Step 2b) that
opens after field validation and before the actual send -- fetches the
template, lets the banker check/uncheck items grouped by category with live
"N selected · N Lender · N Loan Admin" counts, then fires the real send with
the chosen selection. `app/upload/[token]/page.tsx` now groups checklist
items by category. `app/parking-bay/[id]/page.tsx` gained a
`LoanStatusStepper` (Request → Documents → Extraction → Credit review →
Term sheet → Decision → Commitment → Signed → Processing) -- a real "you are
here" indicator over state actually tracked (`extraction_queued_at`), with
everything past Extraction shown as future/not-done since it isn't built.

Verified live end-to-end through the real proxy stack: fetched the real
47-item/27-default template, sent with an explicit 3-item mixed
Lender/Loan-Admin selection, confirmed the Loan Admin item was absent from
both the upload portal and the logged email, uploaded both Lender items and
confirmed `uploads_complete` fired despite the Loan Admin item staying
pending forever, confirmed the parking bay excluded it and `reviewComplete`
was still reachable, and confirmed extraction could still be kicked off
normally. Cleaned up all test DB rows and disk folders afterward.

**Step numbering note:** v3 also inserts two new macro-steps after
Extraction (Credit report, Term sheet & commitment) and pushes the old
"Customer activity log" step from 9 to 11. This project's Step 7/8/9
sections (below and in `TEST_CASES.md`) still use the original v2 numbering
since those steps haven't been touched since v3 arrived -- reconcile the
numbering the next time Step 7+ is revisited, rather than assuming it still
lines up.

## Step 3 — Secure request email — done (logged, not delivered)
`document_requests/email_service.py` composes the exact mockup-template
email (greeting, the request's actual selected Lender items from Step 2b's
checklist, upload link embedding `link_token`, 7-day expiry, anti-phishing
footer, sign-off) and persists it as an append-only `RequestEmail` row -- no
real mail provider (SMTP/SendGrid/etc.) is wired up, per explicit direction
("just log it for now"). Called from both send and resend. New endpoint
`GET /api/requests/<id>/email` returns the latest logged email; the
dashboard's "View email" button opens `EmailPreviewModal` to show it.
14 more tests in `backend/document_requests/tests.py` (55 total across the
whole backend at the time this step was first built).

**Gotcha worth remembering:** Django doesn't wire arbitrary app-logger
`logger.info()` calls to the console by default (only `django`/
`django.server` get a handler) -- added a minimal `LOGGING` dict to
`settings.py` so this (and any future) logging call is actually visible in
the gunicorn console, not silently swallowed.

**Known simplification, resolved by Step 2b:** this originally noted every
request got the same fixed 5-item checklist since Step 2 had no picker UI --
Step 2b (above) added the real customize picker, so this is no longer a gap.

## Step 4 — Customer upload portal — done
`document_requests` gained `ChecklistItem` (one row per selected checklist
item, instantiated at send time), `UploadedFile` (disk storage via
`storage.py`, mirroring appstore's `credit_file_server` pattern -- files
under `settings.UPLOAD_STORAGE_ROOT`, only the relative path in the DB), and
`UploadSession` (20-minute session timer + fraud counters). Public
(no-auth) endpoints: `GET/POST /api/upload/<token>[/documents]`. Banker-side:
`GET /api/requests/<id>/uploads` + `.../uploads/<id>/serve`.
`app/upload/[token]/page.tsx` is the real customer-facing portal (checklist,
live countdown, terminal states for expired/fraud-stopped/complete).
Dashboard gained "Copy link" and a real "View docs" modal. 24 more tests
(79 total across the whole backend).

The Step 3 email's upload link is now a **real, working URL** to this
project's own frontend (`settings.FRONTEND_BASE_URL` + `/upload/<token>`),
not the mockup's fake `upload.freedombankva.com` domain.

**Storage location:** `UPLOAD_STORAGE_ROOT` is set in `.env` to the same
shared folder appstore's `credit_file_server` usecase already uses --
`/home/ismail/Workspace/freedom bank/dev/Credit File Server` (no "2.0") --
per explicit direction, rather than the separate local `uploads/` folder
originally scaffolded (removed). The two apps' folder-naming conventions
differ enough (`(req{id})` here vs `(id{id})` in appstore) that they coexist
in the same root without collision. `config/settings.py`'s hardcoded default
still points at the local `uploads/` dir as a fallback if the env var is
ever unset -- the real value always comes from `.env`.

**Fraud/session guard is honestly scoped:** two deterministic heuristics --
`failed_attempts >= 5` and `total_attempts >= 20` -- not real bot detection.
**Location-jump detection from the mockup copy is NOT implemented** (would
need real IP geolocation infra) and is tracked as a gap in `TEST_CASES.md`,
not silently skipped. A fraud trip logs an alert email to the banker via the
same `RequestEmail` mechanism as Step 3 (`kind='fraud_alert'`).

**Gotcha worth remembering (bit us during this step):** Django's `TestCase`
only sandboxes the database (rolled back per test) -- it does **not**
sandbox filesystem writes. Tests that upload files were, for a while,
writing real files into the actual `UPLOAD_STORAGE_ROOT` on every run,
polluting real dev data. Fixed with a module-level `setUpModule`/
`tearDownModule` in `document_requests/tests.py` that redirects
`UPLOAD_STORAGE_ROOT` to a `tempfile.TemporaryDirectory()` for the whole
test module. Apply the same pattern to any future app that writes to disk
in its views.

## Step 5 — Session terminal states / reference number / confirmation email — done
Turned out to be mostly-already-built: 5.3/5.4/5.5 (fraud termination screen,
logging+alerting, link deactivation) were fully satisfied by Step 4's own
fraud-guard work with no new code needed. The genuinely new pieces:
- `DocumentRequest.reference_number` (`REQ-{year}-{id:04d}`, migration
  `0004_documentrequest_reference_number_and_more`) -- assigned once via
  `_assign_reference_number()` at first send, kept stable across resends
  (unlike `link_token`, which rotates every resend). Unique by construction
  since it's derived from the row's own unique id, no separate counter table.
- `log_completion_confirmation_email()` in `email_service.py` -- fires
  exactly once, the moment the last checklist item completes (inside
  `upload_document_view`, guarded by `status == 'sent'` so a post-completion
  re-upload can't refire it), reusing the same log-only `RequestEmail`
  mechanism as Steps 3/4 (`kind='confirmation'`).
- `upload_info_view` and the requests list both now surface
  `referenceNumber`; the upload portal's "Thanks for uploading" screen shows
  it plus a "Confirmation email sent to {email} from the platform" line;
  the dashboard's Recent Requests row shows "· Reference REQ-2026-####".

10 more tests in `ReferenceNumberAndConfirmationEmailTests`
(`backend/document_requests/tests.py`, 89 total across the whole backend).
Verified live end-to-end through the real proxy stack (login → send → upload
all 5 checklist items → confirmed reference number + confirmation email
content via curl → cleaned up the test DB row and its disk folder under the
shared storage location).

## Step 6 — Parking bay review & review summary — done
`UploadedFile` gained real review fields (`review_status`/`review_comment`/
`reviewed_at`/`reviewed_by` -- migration `0005`), living on the file itself
rather than `ChecklistItem`, so a re-upload after a flag naturally starts a
fresh `pending` review on the new row while the old flagged row (and its
comment) stays in history untouched -- no extra bookkeeping needed for that.

New banker-authenticated endpoints in `document_requests/views.py`:
- `GET /api/requests/<id>/parking-bay` -- per-item file + review state,
  `reviewComplete`/`approvedCount`/`flaggedCount`.
- `POST .../parking-bay/<item_id>/review` -- `{decision: 'approve'|'flag',
  comment}`; flagging without a comment is rejected (400).
- `POST .../parking-bay/send-flags-email` -- bundles *every* currently
  flagged item's comment into one `RequestEmail(kind='review_flags')` to the
  customer; 400 if nothing's flagged. Reuses the same log-only email
  mechanism as Steps 3/4/5 -- still no real mail provider.
- `POST .../parking-bay/kick-start-extraction` -- gated on every uploaded
  item having a decision; queues only the approved ones; sets
  `DocumentRequest.extraction_queued_at` once and refuses to fire twice.

**Deliberately not faked:** `extraction_queued_at` is a real one-time
timestamp, but **Step 7's actual twin-extraction pipeline doesn't exist
yet**, so nothing consumes it -- the gate and the record are real, the
downstream pipeline is honestly still a gap. The document preview in
`app/parking-bay/[id]/page.tsx` is real (not faked) for what the browser can
natively render -- `<img>` for `image/*`, `<iframe>` for `application/pdf` --
with an honest "no inline preview, open/download instead" fallback for
everything else (xlsx, docx, etc.), rather than building/faking a universal
document viewer.

17 more tests in `ParkingBayReviewTests` (`backend/document_requests/tests.py`,
106 total across the whole backend). Frontend: new
`app/parking-bay/[id]/page.tsx` (file list sidebar, preview/review panel,
review-summary table, the two batch actions); dashboard gained a "Review"
button. Verified live end-to-end through the real proxy stack (login → send
→ upload all 5 → approve 4/flag 1 with the required comment → confirmed
review summary counts → sent the bundled flags email → kicked off
extraction, confirmed it can't be queued twice → cleaned up the test DB row
and its disk folder under the shared storage location).

**Bug found and fixed later (user-reported):** the dashboard's status badge
only reflects `DocumentRequest.status` (draft/sent/uploads_complete/...),
which is about the *upload* lifecycle, not review decisions -- a request
with every Lender item uploaded shows the green "Uploads complete" badge
even if one of those files was later flagged in parking-bay review and
needs a re-upload. `_request_json` gained a computed `hasFlaggedItems`
field (`checklist_items.filter(current_file__review_status='flagged').exists()`),
and the dashboard now shows an additional "⚑ Flagged — needs re-upload"
badge alongside the status badge when true. 2 more tests. Found live on a
real request (`REQ-2026-0009`) the user had in their own dashboard, not
synthetic test data -- confirmed the fix against that same request rather
than a fresh one.

## Step 7 — Twin extraction — done (upgraded to real content extraction)
**Scope decision #1 (asked before building this step):** no real OCR/AI
extraction service exists in this project. Presented two options -- (a)
real heuristic content-based extraction, or (b) a real DB-backed stage
machine with no content reading, placeholder extracted values. **The user
picked (b) first.**

**Scope decision #2 (asked again while starting Step 8):** Step 8's mockup
needs real per-value data (dollar amounts, confidence, source pointers) to
review -- option (b) can't produce that. Asked again: honestly rescope
Step 8 to twin-level handoff only, or go back and upgrade Step 7 to real
extraction. **The user chose to upgrade Step 7.** What actually got built:

- `DocumentTwin` (Received -> Classified -> Extracted -> Provenance ->
  Confidence) and `BusinessTwin` (Relationship -> Entities -> Covenant
  ledger -> Indicators -> Allocation), migration `0006`. Real rows, real
  timestamps, one stage at a time via an explicit `POST .../advance` --
  the server always moves to exactly the next stage in `STAGE_ORDER`, so
  skipping is structurally impossible, not just discouraged by the UI.
- `document_requests/extraction.py`'s `classify()` -- still a simple
  deterministic lookup by checklist item name (not file content) for the
  "Classified" stage. Not upgraded in this pass -- there's no real
  document-type classifier, and that's an honest, documented simplification.
- `document_requests/content_extraction.py` (migration `0007` adds
  `ExtractedValue`) -- **now real**. Reads the actual uploaded bytes and
  extracts real values with real libraries that happened to already be
  available in this dev environment (found via `pip3 list` before adding
  anything): `pdfplumber` (PDF text), `python-docx` (docx paragraphs),
  `openpyxl` (direct spreadsheet cell reads -- no regex needed, no
  ambiguity, so these get flat 1.0 confidence), `pytesseract` + the
  `tesseract` system binary (image OCR), plain UTF-8 decode for `.txt`.
  Dollar amounts / percentages / ratios / dates are found via real regex
  over that genuinely-extracted text. Still **no real NLP/AI** -- it can
  find a dollar-shaped number, it can't tell "Total revenue" from "Total
  expenses". Unsupported types (zip, unknown binary) get zero values
  honestly, not a fake result. All five new packages added to
  `requirements.txt` with pinned versions matching what's installed.
- "Provenance"/"Confidence" stages now compute real aggregates over the
  `ExtractedValue` rows (source-pointer count, average confidence, HITL
  count at `CONFIDENCE_ROUTING_THRESHOLD = 0.85`) instead of placeholder
  strings.
- Genuine extraction failures (corrupt/unreadable file) are caught, logged
  as `extract.failed`, returned as a real 400 with the real parser error --
  and the stage does **not** advance, so it's retriable, not a dead end.
- `ExtractionEvent` -- append-only audit log, one row per stage transition
  plus a matching `audit.write` row (same pattern as `RequestEmail`/
  `LoginEvent`).
- Business twin's Covenant-ledger-onward stages are still really gated on
  every document twin reaching at least `extracted`, but still have no real
  covenant/obligation data model behind them -- that part of the original
  scope choice is unchanged by this upgrade.
- Twins are created inside Step 6's `kick_start_extraction_view`, one
  `DocumentTwin` per **approved** file only (flagged files never get one).

31 Step-7 tests total (`TwinExtractionTests` 16, `ContentExtractionUnitTests`
9, `ExtractedValueModelTests` 1, `DocumentTwinContentExtractionAPITests` 5 --
137 across the whole backend). Frontend: `app/extraction/[id]/page.tsx`
gained a real extracted-values table (field/value/source/confidence/status)
once a twin reaches `extracted` or later. Verified live end-to-end through
the real proxy stack twice -- once for the stage-machine pass, once again
for real extraction: uploaded a real PDF (built with `reportlab`) and a real
`.xlsx` (built with `openpyxl`), advanced both twins to `extracted`, and
confirmed the actual `$4,218,400`/`1.14x` text match and the actual sheet/
cell values came back correctly; then uploaded a genuinely corrupt "PDF"
and confirmed the real pdfplumber error surfaced with a 400 and the stage
didn't move. Cleaned up all test DB rows and disk folders afterward.

## Next step when resuming
Step 8 (extraction review & handoff + business twin): HITL review of
extracted values now has real data to work with (`ExtractedValue.confidence`
+ `needs_review`, real source pointers) -- 8.1/8.2 no longer need a scope
conversation. Still needs: "Submit for loan officer review" gated on zero
HITL-pending values remaining; a discrepancy path that emails the customer
verbatim (reuse the Step 6 flag+comment+email pattern) and keeps the
obligation open; document twin versioning on a corrected re-upload; and the
business twin's covenant ledger / DSCR advisory-flag display, which is
still a real gap (no covenant data model exists) worth flagging to the user
before assuming how deep to build it.

## Unrelated work in this session (for context, not blocking)
A separate project, `extract-lab` (`/home/ismail/Workspace/Extarct
Document/extract-lab`), had its cross-written-page "rotate/separate" mode
split reverted back to a single boolean flag — unrelated to this project,
mentioned here only because it happened in the same working session.
