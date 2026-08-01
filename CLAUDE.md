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

## Step 2b correction — checklist config is a profile setting, not a per-request modal (v5)
**A real miss, caught by the user, not by review.** The v3 rebuild above
built a per-request "Customize & Send" modal (`CustomizeModal`) that
appeared after field validation on every single send. When v5 arrived, the
diff-based check that reviewed Step 2 compared byte ranges within the
section and concluded (wrongly) that the modal's content was just extended
with new dashboard widgets -- it never registered that the modal's own
*heading and button copy* had changed: "Checklist configuration — under
profile settings" / "Save configuration" (v5) vs. "Customize & Send Secure
Upload Link" / "Generate Secure Link" (v3). The real change: v5 moved
checklist configuration to a **one-time profile setting**
(`workspace.freedombankva.com/settings/checklist`, opened from the avatar
menu), and "Send secure request" on the dashboard went back to being a
single click that just uses whatever's saved there. Lesson: a byte-range
diff catches *added* content reliably but can silently miss a *renamed/
recontextualized* section with mostly-similar body content -- worth
spot-checking headings and button copy specifically when a diff comes back
looking like "same thing plus more," not just skimming the added lines.

Fixed:
- New `ChecklistPreference` model (migration `0009`) -- one saved selection
  per banker (`OneToOneField` to `User`), `selected_items` stored as JSON.
  Audience is always re-resolved from `CHECKLIST_TEMPLATE` both at save time
  and at send time -- never trusted from what's stored, same principle as
  the original per-request `selectedItems` validation.
- New `GET/POST /api/requests/checklist-preference` -- GET falls back to the
  template's own default selection (with `isSaved: false`) when the banker
  has never saved one, so the settings page always has sensible starting
  checkboxes. POST validates (400 on an unknown item or an empty selection)
  and upserts (`update_or_create`, so re-saving overwrites rather than
  accumulating rows).
- `list_create_view`'s send branch now resolves the checklist in priority
  order: explicit `selectedItems` in the request body (kept -- tests and
  any future scripted/API sends can still override) → the banker's saved
  `ChecklistPreference` → the template's own default. A plain "Send secure
  request" click sends **no** `selectedItems` at all now, so it always
  falls through to the banker's saved preference.
- `CustomizeModal` deleted from `app/dashboard/page.tsx` entirely --
  "Send secure request" is a single click again, same as before Step 2b
  existed. New `app/settings/checklist/page.tsx` carries the same
  categorized-checkbox UI the modal had, now as a real page with a "Save
  configuration" button. Dashboard topbar gained a plain "Checklist
  settings" link (the mockup says "opened from the avatar menu," but this
  project doesn't have a full avatar dropdown yet, so a direct link stood
  in rather than building a menu component for one link) and the factions
  note now reads "...document list comes from your configured checklist"
  with a link into settings.

1 new model, 2 new endpoints, 8 more tests (`ChecklistPreferenceTests` +
one new case in `ChecklistSelectionAtSendTests`), 181 total across the
whole backend. Verified live end-to-end: saved a real 2-item preference,
then sent with a completely bare request body (no `selectedItems` key at
all) and confirmed the created `ChecklistItem` rows matched the saved
preference exactly, not the template default. Cleaned up the test DB row
and the one `ChecklistPreference` row created during verification
afterward.

## Step 2c — Workspace nav & customer activity — done (partial, v5)
`FBOV_Document_Request_Flow_Mock_v5.html` arrived and grew Step 2
substantially: a workspace nav tab bar, a document-estate search bar, a
portfolio-wide stat strip ("218 twins created this month", etc.), a "Loans
in flight by stage" chart, and three sidebar rails (Needs attention / This
week / Portfolio pulse) driven by tickler/reminder scheduling and
covenant/DSCR tracking. Steps 1/3/4/5 were byte-identical between v3 and
v5; Step 6 only gained the same nav bar.

**Asked the user which of this to build, since most of it needs
infrastructure that doesn't exist:** search over extracted values, a
reminder/tickler system, and a covenant/DSCR data model. **Answer: nav bar +
Customer Activity Log only, real data, skip the rest** (search bar, stat
strip, loans-by-stage chart, all three sidebar rails) -- explicitly
documented as a scope decision in `TEST_CASES.md`, not silently dropped.

What got built:
- `WorkspaceNav` (`app/components/WorkspaceNav.tsx`) -- two tabs, Overview
  and Customer activity, not the mockup's five. Parking bay/Loans/Portfolio
  were left out because they don't have a real *global* landing page here
  (parking bay is per-request only; Loans/Portfolio need pipeline stages
  beyond what's built) -- no point linking to something that isn't real.
- `GET /api/requests/activity` + `_activity_events()` in
  `document_requests/views.py` -- assembles a real, chronological,
  per-request event trail entirely from data already logged elsewhere
  (`RequestEmail`, `UploadedFile`, `ExtractionEvent`). No new event-logging
  model needed. `audit.write` rows are filtered out of this human-facing
  view (pure duplicate of the stage event right before them -- still in the
  raw audit trail via admin, just not shown here).
- `app/activity/page.tsx` -- one card per non-draft request, dot-typed
  timeline (bank/customer/system/alert) matching the mockup's legend.

5 more tests in `CustomerActivityTests` (`backend/document_requests/tests.py`,
160 total across the whole backend). Verified live against real production
data already in the dev database (not synthetic test rows) -- confirmed
real upload/review/twin events appear in the correct chronological order
with `audit.write` correctly excluded.

**Gotcha caught by the user, fixed same session:** the nav bar only got
wired into the dashboard and activity pages at first -- v5 actually adds it
to Steps 6 and 7 too (parking bay, extraction), not just Step 2. Added
`<WorkspaceNav />` to `app/parking-bay/[id]/page.tsx` and
`app/extraction/[id]/page.tsx` as well.

## Step 2d — Search, stat strip, loans-by-stage, needs attention — done (partial, v5)
Went back and re-examined the "needs infrastructure that doesn't exist" list
from Step 2c, number by number instead of writing the whole group off.
**Most of it turned out to be real, simple queries over data already in the
database** -- the earlier scope call was too conservative. Asked the user
again with the more granular breakdown; **answer: build all the real-data
ones.**

What's real now:
- **Search** (`GET /api/requests/search?q=`) -- substring match
  (`icontains`) across `DocumentRequest` (borrower/company/reference/email),
  `ChecklistItem.name`, and `ExtractedValue` (field_name/value). No
  semantic search, just literal text matching -- honestly labeled as such.
- **Stat strip** -- `twinsCreatedThisMonth` (real count),
  `pctValuesAutoVerified` (real: verified/total `ExtractedValue`s at the
  `CONFIDENCE_ROUTING_THRESHOLD` cutoff, `null` -- not a fake 0% -- when no
  values exist anywhere yet), `avgRequestToExtractionDays` (real: average
  `extraction_queued_at - sent_at`, `null` when nothing's reached extraction).
- **Loans by stage** -- only the two real stages (Documents, Extraction).
  Credit review/Term sheet/Decision/Commitment/Signed/Processing are
  omitted, not shown as fake zeros -- same principle as the parking-bay
  `LoanStatusStepper`.
- **Needs attention** (`GET /api/requests/needs-attention`) -- fraud-stopped
  sessions (real `fraud_reason`), flagged documents (reuses the
  `hasFlaggedItems` query, shows the real comment), and a single aggregate
  "N values in HITL queue" count from real low-confidence `ExtractedValue`
  rows -- honestly labeled as having no review/handoff screen yet since
  Step 8 isn't built.
- **Still not built, explicit gap:** "This week" (ticklers, payment-due
  notices, expected annual-review docs) and "Portfolio pulse" (covenant
  compliance %, DSCR watchlist, advisory flags, "docs collected without
  chasing" %) -- both genuinely need a reminder/scheduling system and/or a
  covenant data model that don't exist here.

13 more tests (`NeedsAttentionTests`, `SearchTests`, two new `MetricsTests`
cases), 173 total across the whole backend. Frontend:
`app/dashboard/page.tsx` gained a debounced live-search box (dropdown
results link straight into parking bay), a `.statstrip` panel (new CSS
class in `globals.css`), a "Loans in flight" segmented bar (only renders
once something's actually in flight), and a "Needs attention" panel (only
renders when non-empty -- no empty-state chrome for a feature with nothing
to show). Verified live against real production data: real flagged-doc
entries, real loans-by-stage counts, real search matches on "Intics"
returning the actual dev-database requests.

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

## Step 3 upgrade — real direct-to-MX email delivery (no provider, no credentials)
Asked which SMTP provider to wire up; the user pointed at the sibling
**StackPulse** project's own email implementation as the pattern to follow
instead of a third-party provider. Read StackPulse's
`EmailService`/`DirectMailSender`/`MxResolver`/`DomainWhitelistService`
(Java/Spring) and ported the same architecture to Python: **direct-to-MX
delivery** -- resolve the recipient domain's real MX record via DNS, then
connect straight to that mail server and hand the message off with
opportunistic STARTTLS. No SMTP relay, no provider account, no API key or
password anywhere in this codebase -- which also sidestepped the earlier
"where do the credentials go" question entirely, since there are none.

What got built:
- `document_requests/mail_delivery.py` -- `_resolve_mx()` (real DNS MX
  lookup via `dnspython`, cached, falls back to the domain itself per
  RFC 5321 if the lookup fails), `_is_domain_allowed()` (fails closed --
  `MAIL_ALLOWED_DOMAINS` empty by default blocks everything, same as
  StackPulse's `DomainWhitelistService`), `send_direct_email()` (real
  `smtplib` SMTP session: EHLO, STARTTLS if offered, `sendmail`). Returns
  `(attempted, delivered)` so "never even tried" is distinguishable from
  "tried and failed" -- never raises.
- `RequestEmail` gained `delivery_attempted`/`delivered` (migration
  `0010`). `email_service.py` was rewritten around one shared
  `_log_and_deliver()` helper -- the audit row is always created first,
  *then* real delivery is attempted and the row updated with the outcome,
  so a delivery failure never loses the audit trail.
- 8 new settings (`MAIL_ENABLED`, `MAIL_FROM_ADDRESS`, `MAIL_FROM_NAME`,
  `MAIL_ALLOWED_DOMAINS`, `MAIL_SMTP_PORT`, `MAIL_TEST_SERVER`,
  `MAIL_TIMEOUT_SECONDS`, `MAIL_DNS_TIMEOUT_SECONDS`) in `.env`/
  `config/settings.py`. `MAIL_TEST_SERVER` is StackPulse's own escape
  hatch, ported as-is: set to `host:port` and every outbound email routes
  there instead of doing real MX resolution.
- `EmailPreviewModal` in `app/dashboard/page.tsx` now shows a real
  "✓ Delivered" / "✕ Delivery failed" badge instead of a fixed "never
  delivered" note.

**Honestly still not solved, and can't be by code alone:** `freedombankva.com`
is a fictional domain with no real SPF/DKIM/DMARC DNS records, so even a
protocol-correct direct-to-MX send would likely be spam-flagged or rejected
by a real major mail provider (Gmail, Outlook, etc.) -- sending
*reputation* isn't something code can fix, only owning a real domain with
real DNS records can. This is the same tradeoff StackPulse itself accepted.
Bounce handling is also out of scope for the same structural reason --
direct-to-MX has no webhook to receive bounces on, unlike SendGrid/SES/etc.

**Gotcha discovered this session:** outbound port 25 is blocked in this dev
sandbox (confirmed with a direct raw-socket connection test -- times out).
Real delivery to the actual internet can't be verified from here. Verified
instead, for real: (a) DNS MX resolution against `gmail.com` returned real
records, (b) a real (non-mocked) local `python3 -m smtpd -c DebuggingServer`
instance, reached via `MAIL_TEST_SERVER`, received a complete correctly-
formed message through the real app (login → send → real SMTP transaction)
with the real checklist content and real upload link intact in the
base64-decoded body -- proof the full code path works, even though true
internet-facing delivery needs a host where port 25 egress is open.

**Architecture note, not fixed in this pass:** delivery is currently
*synchronous* inside the Django request/response cycle -- no task queue
(Celery/RQ) exists in this project, unlike StackPulse's Spring `@Async`. A
slow or blocked SMTP hand-off delays the HTTP response by up to
`MAIL_TIMEOUT_SECONDS` (10s default). Worth revisiting with a background
worker if real-world latency becomes noticeable; not built now to avoid
introducing infrastructure this project doesn't otherwise have.

13 new tests (`MailDeliveryTests` with `smtplib.SMTP` mocked so the
automated suite never touches the real network, plus
`EmailDeliveryIntegrationTests`), 190 total across the whole backend. A
module-level `override_settings(MAIL_ENABLED=False)` in `tests.py`
guarantees the rest of the suite can never attempt a real send regardless
of what `.env` happens to contain. Cleaned up: killed the local debug SMTP
listener, reverted `.env`'s `MAIL_TEST_SERVER` back to empty (real-MX mode)
and `MAIL_ALLOWED_DOMAINS` to `intics.ai` (per direct instruction) once
verification was done, and deleted the two test `DocumentRequest` rows
created during live verification.

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
