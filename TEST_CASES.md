# Credit File Server 2.0 — Test Case Specification

Derived from `FBOV_Document_Request_Flow_Mock_v2.html` (9-step commercial-loan
document request flow). **Steps 1 (banker sign-in), 2 (dashboard / create &amp;
send request), 2b (customize & send secure upload link), 2c (workspace nav &
customer activity), 2d (search, stat strip, loans-by-stage, needs attention),
3 (secure request email), 4 (customer upload portal), 5 (session terminal
states / reference number / confirmation email), 6 (parking bay review &
review summary), and 7 (twin extraction — real content extraction, see its
scope-decision note)** are actually built; their cases are marked ✅
Automated and map to `backend/accounts/tests.py` and
`backend/document_requests/tests.py` (173 tests total, all passing). Steps
8–9 are 🔲 Planned — this is the test spec to build against, not yet
runnable code, since those screens are still design-concept mockup only.

**Mockup note:** Steps 1-6 were rebuilt against `FBOV_Document_Request_Flow_Mock_v3.html`,
then Step 2 was extended twice more once `FBOV_Document_Request_Flow_Mock_v5.html`
was provided -- first workspace nav + customer activity (2c), then search/
stats/loans-by-stage/needs-attention (2d, after re-examining what was
initially written off as needing infrastructure that doesn't exist) --
v2/v3 are kept for history. v3 also renumbers/adds steps beyond
6 (a new Step 9 "Credit report" and Step 10 "Term sheet & commitment" push
the old Step 9 "Customer activity log" to Step 11) -- the "Step 7/8/9"
sections below still use the original v2 numbering since those steps
haven't been revisited against v3/v5 yet. Reconcile the numbering when
Step 7+ is next touched.

Status legend: ✅ Automated · 🟡 Manual-only (UI, needs a human/browser) · 🔲 Planned (feature not built yet)

---

## Step 1 — Banker Sign-In

### Backend: `POST /api/auth/login`

| ID | Case | Given | When | Then | Status |
|----|------|-------|------|------|--------|
| 1.1 | Valid credentials succeed | Active user exists | POST correct email+password | 200, `user` object returned, session cookie set | ✅ `test_login_success_returns_user_and_sets_session` |
| 1.2 | Session persists across requests | Logged in via 1.1 | GET `/api/auth/me` with session cookie | 200, same user returned | ✅ (same test) |
| 1.3 | Email match is case-insensitive | User `banker@…` exists | POST with `BANKER@…` + correct password | 200, login succeeds | ✅ `test_login_is_case_insensitive_on_email` |
| 1.4 | Wrong password rejected | User exists | POST correct email, wrong password | 401, `{error}` | ✅ `test_login_wrong_password_rejected` |
| 1.5 | Unknown email rejected | No such user | POST unregistered email | 401, `{error}` | ✅ `test_login_unknown_email_rejected` |
| 1.6 | No account-existence leak | — | Compare error body of 1.4 vs 1.5 | Identical error message both cases | ✅ `test_login_wrong_password_and_unknown_email_give_identical_error` |
| 1.7 | Missing email rejected | — | POST `{password}` only | 400, no session created | ✅ `test_login_missing_email_rejected` |
| 1.8 | Missing password rejected | — | POST `{email}` only | 400, no session created | ✅ `test_login_missing_password_rejected` |
| 1.9 | Deactivated account cannot sign in | User with `is_active=False` | POST correct credentials | 401 (Django's `ModelBackend` excludes inactive users) | ✅ `test_inactive_user_cannot_log_in` |
| 1.10 | Empty-body request | — | POST with no fields at all | 400, handled gracefully (no 500) | 🔲 Planned — add explicit case |
| 1.11 | SQL/script injection in email field | — | POST `email="' OR 1=1--"` | 400/401, no server error, no data leak | 🔲 Planned |
| 1.12 | Excessively long input | — | POST 10,000-char password | Handled without 500, rejected normally | 🔲 Planned |
| 1.13 | Rate limiting / brute-force throttling | — | 20 failed attempts in quick succession for one account | Requests get throttled/locked (not currently implemented) | 🔲 Planned — **no lockout exists yet**, flag as a gap before real production use |

### Backend: `GET /api/auth/me`

| ID | Case | Given | When | Then | Status |
|----|------|-------|------|------|--------|
| 1.14 | Anonymous session | No login | GET `/api/auth/me` | 200, `{"user": null}` (not a 401) | ✅ `test_me_returns_null_when_not_signed_in` |
| 1.15 | Authenticated session | Logged in | GET `/api/auth/me` | 200, correct user payload | ✅ `test_me_returns_user_after_login` |

### Backend: `POST /api/auth/logout`

| ID | Case | Given | When | Then | Status |
|----|------|-------|------|------|--------|
| 1.16 | Logout requires auth | Not logged in | POST `/api/auth/logout` | 403 (DRF's `SessionAuthentication` has no `WWW-Authenticate` challenge, so `IsAuthenticated` denies with 403, not 401 — this is standard DRF behavior, not a bug) | ✅ `test_logout_requires_authentication` |
| 1.17 | Logout clears session | Logged in | POST logout, then GET `/api/auth/me` | `me` now returns `{"user": null}` | ✅ `test_logout_clears_session` |

### Backend: Audit log (`LoginEvent`) — "every sign-in audited"

| ID | Case | Given | When | Then | Status |
|----|------|-------|------|------|--------|
| 1.18 | Successful login is logged | — | Valid login | `LoginEvent(success=True, user=<the user>)` created | ✅ `test_successful_login_creates_audit_event` |
| 1.19 | Failed login is logged | — | Wrong password | `LoginEvent(success=False, user=None)` created | ✅ `test_failed_login_creates_audit_event` |
| 1.20 | Unknown-email attempt still logged | — | Login attempt for email with no account | `LoginEvent(email_attempted=<that email>, success=False)` exists | ✅ `test_login_attempt_for_unknown_email_still_logged` |
| 1.21 | Malformed request doesn't pollute the log | — | POST with no fields (400 before auth attempted) | No new `LoginEvent` row | ✅ `test_malformed_request_does_not_create_audit_event` |
| 1.22 | Audit log is append-only in admin | — | Inspect `LoginEventAdmin` | `has_add_permission` and `has_change_permission` both `False` | ✅ `test_audit_log_is_read_only_via_admin` |
| 1.23 | IP address captured | — | Login via a request with `X-Forwarded-For` set | `LoginEvent.ip_address` reflects the forwarded IP, not the proxy's | 🔲 Planned — add explicit assertion (helper exists, untested directly) |
| 1.24 | Deletion is not exposed anywhere | — | Attempt `DELETE` via admin/API on a `LoginEvent` | No delete path exists in `admin.py`/`urls.py` | 🔲 Planned — confirm no delete route ever gets added |

### Frontend: Sign-in page (`app/page.tsx`) — 🟡 manual/browser cases

| ID | Case | Steps | Expected | Status |
|----|------|-------|----------|--------|
| 1.25 | Happy path sign-in | Enter valid email+password, click Sign in | Redirects to `/dashboard` | 🟡 |
| 1.26 | Wrong password shows inline error | Enter valid email, wrong password | Red `formnote` shows "Invalid email or password." (not a generic "backend down" message now that the backend exists) | 🟡 |
| 1.27 | Backend unreachable | Stop the Django server, submit the form | "Could not reach the sign-in service — is the backend running?" shown, no crash | 🟡 |
| 1.28 | Already-signed-in session skips the form | Sign in, then visit `/` directly | Redirects straight to `/dashboard` instead of showing the form again (via `/api/auth/me` check on mount) | 🟡 |
| 1.29 | Sign out returns to the form | From `/dashboard`, click "Sign out" | Redirects to `/`, form shown, fields empty | 🟡 |
| 1.30 | Required-field browser validation | Click Sign in with both fields empty | Native HTML5 validation blocks submit (both inputs `required`) | 🟡 |
| 1.31 | SSO button placeholder | Click "Continue with bank SSO" | Shows "Bank SSO isn't wired up yet." note, no crash, no fake success | 🟡 |
| 1.32 | MFA notice always visible | Load the sign-in form | "🛡️ Multi-factor authentication required on every session" text present (copy-only — no real MFA challenge exists yet) | 🟡 |
| 1.33 | Responsive layout | View at <760px width | `.login .side` (navy branding panel) hides, form takes full width | 🟡 |
| 1.34 | `/api/*` proxy reaches Django | With both dev servers running, `fetch('/api/auth/me')` from the browser | Resolves via the Next.js rewrite to `localhost:8001`, not a 404 | ✅ verified manually this session (curl-level); 🟡 for actual browser confirmation |

---

## Step 2 — Credit Audit Dashboard: Create & Send Request ✅ Built (partial)

Copy requirement: *"Each field is verified live... only then does Send secure
request fire the encrypted, single-purpose link."*

**Honesty note:** the mockup's copy claims "deliverable address · domain
verified" and "matches state registry" -- those need a real mail-verification
service and a business registry API, which don't exist here. Validation is
scoped to real format checks only (10-digit phone, basic email format,
non-empty names); hint wording says "Valid email format" / "Looks good", not
a false claim of deliverability or registry matching. That's a deliberate
scope decision, tracked as 2.3b/2.4b below rather than silently faked.

Backend: `document_requests` app, tests in `backend/document_requests/tests.py`.
Frontend: `app/dashboard/page.tsx`.

| ID | Case | Given | When | Then | Status |
|----|------|-------|------|------|--------|
| 2.1 | Valid fields all pass | — | POST `/api/requests/validate` with all 4 fields well-formed | All four `{ok: true}` | ✅ `test_all_valid_fields_pass` |
| 2.2 | Phone format validation | — | Phone `703-55-019` (9 digits) | `phone.ok = false`, "Enter a valid 10-digit phone number" (matches mockup copy exactly) | ✅ `test_phone_with_too_few_digits_rejected` |
| 2.2b | Phone formatting characters ignored | — | `(703) 555-1234` | `phone.ok = true` -- punctuation/spacing stripped before counting digits | ✅ `test_phone_formatting_characters_ignored` |
| 2.2c | Phone too many digits rejected | — | 14-digit string | `phone.ok = false` | ✅ `test_phone_with_too_many_digits_rejected` |
| 2.3 | Email format validation | — | `priya.meridianlogistics.com` (no `@`) | `email.ok = false` | ✅ `test_email_missing_at_sign_rejected` |
| 2.3a | Email missing domain dot | — | `priya@meridianlogistics` | `email.ok = false` | ✅ `test_email_missing_domain_dot_rejected` |
| 2.3b | Email "deliverable/domain verified" claim | — | — | **Not implemented** -- would need a real mail-verification/MX-check service | 🔲 Planned (scope decision, see honesty note) |
| 2.4 | Borrower/company name required | — | Blank or whitespace-only name | `.ok = false`, "... is required" | ✅ `test_blank_borrower_name_rejected`, `test_blank_company_name_rejected` |
| 2.4b | Company "matches state registry" claim | — | — | **Not implemented** -- would need a real business registry API | 🔲 Planned (scope decision, see honesty note) |
| 2.5 | Validate endpoint requires auth | Not logged in | POST `/api/requests/validate` | 403 | ✅ `test_validate_requires_authentication` |
| 2.6 | Send with all-valid fields creates a sent request | — | POST `action=send` | 201, `status: "sent"`, `linkExpiresAt` set (7 days out) | ✅ `test_send_with_all_valid_fields_creates_sent_request` |
| 2.7 | Each send gets a unique link token | — | Send twice | Two different `link_token` values in the DB | ✅ `test_send_generates_a_unique_link_token` |
| 2.8 | Server re-validates on send (client isn't trusted) | — | POST `action=send` with an invalid phone | 400, **no row created** | ✅ `test_send_rejects_invalid_phone_server_side` |
| 2.9 | Server re-validates email on send | — | POST `action=send` with a malformed email | 400 | ✅ `test_send_rejects_invalid_email_server_side` |
| 2.10 | Draft doesn't require phone/email validity | — | POST `action=draft` with blank phone/email | 201, `status: "draft"` | ✅ `test_draft_does_not_require_valid_phone_or_email` |
| 2.11 | Draft still requires a borrower name | — | POST `action=draft` with blank name | 400 | ✅ `test_draft_requires_at_least_a_borrower_name` |
| 2.12 | Draft has no link token | — | Create a draft | `linkExpiresAt: null` | ✅ `test_draft_has_no_link_token` |
| 2.13 | List/create requires auth | Not logged in | GET `/api/requests` | 403 | ✅ `test_list_requires_authentication` |
| 2.14 | Active-requests metric counts only `sent` | 2 sent, 1 draft, 1 expired | GET `/api/requests` | `metrics.activeRequests == 2` | ✅ `test_active_requests_counts_only_sent_status` |
| 2.15 | Untracked metrics are `null`, never a faked `0` | — | GET `/api/requests` | `docsInParkingBay` and `sessionsEndedFraud` both `null` (Step 4/fraud-guard don't exist yet) | ✅ `test_untracked_metrics_are_null_not_faked_zero` |
| 2.16 | List includes every status | Mixed draft + sent rows | GET `/api/requests` | Both appear in `requests[]` | ✅ `test_list_includes_all_requests_regardless_of_status` |
| 2.17 | Resend on an expired link re-sends | Request with `status=expired` | POST `/api/requests/<id>/resend` | 200, `status: "sent"`, new `linkExpiresAt` | ✅ `test_resend_on_expired_request_reissues_link_and_sets_sent` |
| 2.18 | Resend issues a genuinely new token | Old token `old-token-123` | Resend | Token changes to something else | ✅ `test_resend_generates_a_new_token_different_from_before` |
| 2.19 | Resend blocked once uploads are complete | `status=uploads_complete` | POST resend | 400, no-op | ✅ `test_resend_blocked_once_uploads_are_complete` |
| 2.20 | Resend on a nonexistent request | — | POST resend for an unknown id | 404 | ✅ `test_resend_on_nonexistent_request_404s` |
| 2.21 | "View docs" disabled for uploads-complete rows | Frontend, `uploads_complete` row | Render Recent requests | Button disabled with tooltip "Step 4 ... isn't built yet" (honest placeholder, not a dead click) | 🟡 |
| 2.22 | Per-field live validation on blur | Frontend | Blur out of the phone field with a bad number | Red border + hint appear immediately, without submitting the form | 🟡 |
| 2.23 | Form clears after a successful send/draft | Frontend | Send or Save draft succeeds | All 4 fields reset, hints cleared | 🟡 |
| 2.24 | Dashboard redirects anonymous users | Frontend, no session | Visit `/dashboard` directly | Redirects to `/` | 🟡 |
| 2.25 | Duplicate request for same borrower+company | — | Send a second active request for an applicant who already has one active | 🔲 Planned -- currently allowed (no dedupe check exists yet); decide whether this should warn/block |
| 2.26 | **Next.js trailing-slash gotcha (regression guard)** | — | `fetch('/api/requests/')` (trailing slash) through the Next.js rewrite | Must resolve to JSON, not a redirect loop -- Next strips the trailing slash *before* the rewrite runs, which silently breaks any Django route that only exists at the slash form. Fixed by giving the collection endpoint an exact no-slash route in `config/urls.py`; regressions here would be silent (returns a redirect body, not an error) | ✅ verified manually this session; no automated test yet -- 🔲 worth adding an explicit proxy-level test if a JS test harness gets added later |

---

## Step 2b — Customize & Send Secure Upload Link ✅ Built (v3 mockup)

Copy requirement: *"Selected items are added to the internal checklist either
way — but only Lender items ever appear to the customer through the link;
Loan Admin items stay internal."* Replaces the old fixed 5-item
`DEFAULT_CHECKLIST` with the v3 mockup's real ~50-item master template
across 8 categories, each tagged Lender (customer-facing) or Loan Admin
(internal-only).

**Scope decisions, made explicitly with the user before building:**
- Loan Admin items get **real** `ChecklistItem` tracking (visible on the
  banker's side, counted in the picker), but there's **no upload mechanism
  for them yet** -- that's a documented, honest gap, not a silently broken
  feature. They stay `status='pending'` forever; completion/review/metrics
  logic is defined purely in terms of Lender items so this doesn't block
  anything.
- Custom item add/remove (shown in the mockup's "+ Add item" row) is **not
  built** in this pass -- bankers pick from the fixed master template only.
- The template's default-selected set (27 of 47 items: 12 Lender + 15 Loan
  Admin) mirrors the mockup's own example exactly, verified item-for-item
  against its "12 customer-facing · 16 internal" count (which includes one
  demo-only custom item this project doesn't support) -- it is not driven by
  any real loan-type/product rule engine, since none exists here.

Backend: `checklist.py`'s `CHECKLIST_TEMPLATE` (the master data),
`ChecklistItem` gained `category`/`audience` fields (migration `0008`). New
`GET /api/requests/checklist-template` endpoint; `POST /api/requests` gained
an optional `selectedItems: [{category, name}]` field -- server resolves the
real audience from the template (never trusts a client-supplied audience)
and 400s on an unknown item. Falls back to the default selection when
omitted, so every pre-existing "send" test/flow keeps working unchanged.
Tests in `ChecklistTemplateTests`, `ChecklistSelectionAtSendTests`,
`LenderLoanAdminSplitTests` (`backend/document_requests/tests.py`, 27
tests total for this feature, 153 across the whole backend).
Frontend: `app/dashboard/page.tsx` gained a `CustomizeModal` (Step 2b) that
opens after field validation and before send -- fetches the template, lets
the banker check/uncheck items grouped by category with live Lender/Loan
Admin counts, and only then fires the actual send.

| ID | Case | Given | When | Then | Status |
|----|------|-------|------|------|--------|
| 2b.1 | Template endpoint requires auth | Not logged in | GET checklist-template | 403 | ✅ `test_template_endpoint_requires_auth` |
| 2b.2 | Template grouped by category, real order | — | GET checklist-template | Categories match `checklist.CATEGORIES` order exactly | ✅ `test_template_groups_items_by_category_in_order` |
| 2b.3 | Template item count matches the master list | — | GET checklist-template | Total items across all categories == `len(CHECKLIST_TEMPLATE)` (47) | ✅ `test_template_total_item_count_matches_master_list` |
| 2b.4 | Template reflects real default-selected + audience per item | — | GET checklist-template | e.g. "Corporate Resolution" -> selected, Lender; "Certificate of Fact" -> not selected, Loan Admin | ✅ `test_template_reflects_default_selection_and_audience` |
| 2b.5 | No `selectedItems` falls back to the real default | — | POST `action=send`, no selection | Created items match the template's default-selected set exactly (27 items) | ✅ `test_no_selection_falls_back_to_real_default`, `test_default_selection_has_the_documented_lender_loan_admin_split` — also verified live |
| 2b.6 | Explicit selection creates exactly those items | 3-item selection | POST `action=send` | Exactly those 3 `ChecklistItem` rows, in order | ✅ `test_explicit_selection_creates_exactly_those_items` |
| 2b.7 | Audience is server-resolved, not client-supplied | Payload forges `audience: 'loan_admin'` on a real Lender item | POST `action=send` | Created item's audience is the template's real value (`lender`), forged value ignored | ✅ `test_audience_is_server_resolved_not_client_supplied` |
| 2b.8 | Unknown checklist item rejected | Bogus `{category, name}` | POST `action=send` | 400, no `DocumentRequest` row created | ✅ `test_unknown_checklist_item_is_rejected` |
| 2b.9 | Loan Admin items never appear to the customer | Mixed Lender/Loan Admin selection | GET upload portal / logged email | Loan Admin item absent from both | ✅ `test_upload_portal_never_shows_loan_admin_items`, `test_email_never_mentions_loan_admin_items` — also verified live |
| 2b.10 | Customer can't upload against a Loan Admin item | Loan Admin item id | POST upload with that id | 400, item stays `pending` | ✅ `test_customer_cannot_upload_against_a_loan_admin_item` |
| 2b.11 | Completion ignores Loan Admin items | All Lender items uploaded, Loan Admin item never touched | — | `status` -> `uploads_complete` anyway; Loan Admin item stays `pending` forever | ✅ `test_uploads_complete_once_all_lender_items_done_even_with_loan_admin_pending` — also verified live |
| 2b.12 | Parking bay / review-completeness ignore Loan Admin items | Same mix | GET parking-bay | Loan Admin item absent from the list; `reviewComplete` reachable once only the Lender items are reviewed | ✅ `test_parking_bay_excludes_loan_admin_items`, `test_review_complete_ignores_loan_admin_items` — also verified live |
| 2b.13 | Customize modal opens after field validation, before send | Frontend | Click "Customize & send" with valid fields | Modal opens with the real template, correct default checkboxes and live counts | 🟡 (backend verified live via curl; modal itself not independently automated) |

---

## Step 2c — Workspace Nav & Customer Activity ✅ Built (v5 mockup)

**Scope decision, made explicitly with the user:** v5's Step 2 additions
split cleanly into things buildable from data this project already logs
(the workspace nav bar, a real per-request event trail) vs. things needing
infrastructure that doesn't exist (search, portfolio stats, ticklers,
covenants). **This section covers the first group.** See Step 2d below for
the second pass, where most of the "infrastructure that doesn't exist"
group turned out to be buildable for real after all, once broken down
number by number.

- `WorkspaceNav` shows two tabs -- Overview and Customer activity -- not the
  mockup's five (Overview / Customer activity / Parking bay / Loans /
  Portfolio). Parking bay, Loans, and Portfolio don't have a real *global*
  landing page in this app (parking bay is per-request only; Loans/Portfolio
  need pipeline stages beyond what's built) -- omitted rather than linked to
  something that doesn't exist. It appears on all four real workspace
  screens (dashboard, activity, parking bay, extraction) -- v5 adds the same
  nav bar to Steps 6 and 7 too, not just Step 2.
- The Customer Activity screen's event trail is assembled entirely from data
  already logged elsewhere (`RequestEmail`, `UploadedFile`, `ExtractionEvent`)
  -- no new event-logging model was needed. `audit.write` rows are excluded
  from this human-facing view (they duplicate the stage event immediately
  before them -- still visible in the raw admin/audit trail, just not here).

Backend: new `GET /api/requests/activity` endpoint, `_activity_events()` in
`document_requests/views.py`. Tests in `CustomerActivityTests`
(`backend/document_requests/tests.py`, 5 tests).
Frontend: new `app/components/WorkspaceNav.tsx` (dashboard, activity,
parking bay, extraction), new `app/activity/page.tsx`.

| ID | Case | Given | When | Then | Status |
|----|------|-------|------|------|--------|
| 2c.1 | Activity requires auth | Not logged in | GET `/api/requests/activity` | 403 | ✅ `test_activity_requires_auth` |
| 2c.2 | Draft requests excluded | A draft + a sent request | GET activity | Only the sent one appears | ✅ `test_activity_excludes_drafts` |
| 2c.3 | Send event is real | Request just sent | GET activity | "Secure request sent" event present, timestamp matches the logged email | ✅ `test_activity_includes_the_sent_email_event` |
| 2c.4 | Upload + review events, chronological | Upload then flag a document | GET activity | Both events present, `at` timestamps strictly non-decreasing (oldest first, matching the mockup's reading order) | ✅ `test_activity_includes_upload_and_review_events_in_chronological_order` — also verified live against real data |
| 2c.5 | Twin/business-twin events included, `audit.write` excluded | Extraction kicked off | GET activity | `document_twin.received` / `business_twin.relationship` present; `audit.write` absent | ✅ `test_activity_twin_events_included_but_audit_write_excluded` |

---

## Step 2d — Search, Stat Strip, Loans-by-Stage & Needs Attention ✅ Built (partial — v5 mockup)

**Scope decision #2 on this same set of widgets:** re-examined the
"infrastructure that doesn't exist" list from Step 2c number by number
instead of writing the whole group off. Result: search, the stat strip, and
"Needs attention" turned out to be real, simple queries over data already
in the database -- only genuinely un-buildable pieces (tickler/reminder
scheduling, covenant/DSCR tracking, "This week"/"Portfolio pulse" rails)
stayed deferred.

- **Search** -- real substring matching (`icontains`) over
  `DocumentRequest` (borrower/company/reference/email), `ChecklistItem`
  (name), and `ExtractedValue` (field name/value). No semantic/AI search --
  it can't find "documents about cash flow", only literal text matches.
- **Stat strip** -- `twinsCreatedThisMonth` (real count), `pctValuesAutoVerified`
  (real: `confidence >= CONFIDENCE_ROUTING_THRESHOLD` / total, `null` when
  zero values exist -- not a fake 0%), `avgRequestToExtractionDays` (real:
  average of `extraction_queued_at - sent_at` across requests that reached
  extraction, `null` when none have). "Ticklers scheduled" and "covenants
  tracked" are NOT included -- no such systems exist.
- **Loans by stage** -- only the two real stages this project tracks,
  Documents and Extraction. The mockup's Credit review/Term sheet/Decision/
  Commitment/Signed/Processing stages are omitted entirely rather than shown
  as a fake 0 (same principle as the parking-bay `LoanStatusStepper`).
- **Needs attention** -- three real sources: fraud-stopped sessions
  (`UploadSession.fraud_reason`), flagged documents (`hasFlaggedItems`'
  same underlying query), and a single aggregate count of low-confidence
  `ExtractedValue` rows ("N values in HITL queue") -- honestly labeled as
  having no review/handoff screen yet, since Step 8 isn't built. The
  mockup's tickler-escalation item is NOT included -- no reminder system.
- **Not built, explicit gap:** "This week" (ticklers, payment-due
  notifications, expected annual-review docs) and "Portfolio pulse"
  (covenant compliance %, DSCR watchlist, advisory flags, "docs collected
  without chasing" %) -- all need a reminder/scheduling system and/or a
  covenant data model that don't exist in this project.

Backend: `_stat_strip_metrics()` / `_loans_by_stage()` folded into
`GET /api/requests`'s existing `metrics` object; new `GET
/api/requests/needs-attention` and `GET /api/requests/search` endpoints in
`document_requests/views.py`. Tests in `NeedsAttentionTests`, `SearchTests`,
plus two new cases in `MetricsTests` (13 tests total for this pass, 173
across the whole backend).
Frontend: `app/dashboard/page.tsx` gained a live-search input (debounced,
dropdown results linking into parking bay), a `.statstrip` panel, a
"Loans in flight" segmented bar (only rendered once there's at least one
loan in flight -- no empty chart), and a "Needs attention" panel (only
rendered when non-empty).

| ID | Case | Given | When | Then | Status |
|----|------|-------|------|------|--------|
| 2d.1 | Stat-strip metrics are `null`, not a fake 0, when nothing exists | Fresh DB | GET `/api/requests` | `pctValuesAutoVerified` and `avgRequestToExtractionDays` both `null`; `twinsCreatedThisMonth` a real (legitimately 0) count | ✅ `test_stat_strip_metrics_are_null_not_fake_zero_when_nothing_exists_yet` |
| 2d.2 | Loans-by-stage counts only the two real stages | One sent, not-yet-queued request | GET `/api/requests` | `{documents: 1, extraction: 0}` | ✅ `test_loans_by_stage_counts_only_the_two_real_stages` — also verified live |
| 2d.3 | Needs-attention requires auth | Not logged in | GET needs-attention | 403 | ✅ `test_requires_auth` (NeedsAttentionTests) |
| 2d.4 | Fraud case surfaces with its real reason | Guard tripped | GET needs-attention | `type: 'fraud'` item, detail matches the real `fraud_reason` | ✅ `test_fraud_stopped_request_surfaces` — also verified live against real data |
| 2d.5 | Flagged document surfaces with its real comment | Item flagged | GET needs-attention | `type: 'flagged'` item, detail == the real review comment verbatim | ✅ `test_flagged_document_surfaces` — also verified live |
| 2d.6 | Low-confidence values surface as one aggregate count | Mixed-confidence `ExtractedValue`s | GET needs-attention | Single `type: 'hitl'` item, count matches real rows below threshold | ✅ `test_low_confidence_values_surface_as_a_single_hitl_count` |
| 2d.7 | Search requires auth | Not logged in | GET search | 403 | ✅ `test_requires_auth` (SearchTests) |
| 2d.8 | Search matches request/checklist-item/extracted-value fields | Real data with a known substring | GET `search?q=...` | Correct `kind` + `requestId` per match | ✅ `test_matches_request_by_company_name`, `test_matches_checklist_item_name`, `test_matches_extracted_value` — also verified live |
| 2d.9 | Empty query / no match returns empty, not an error | — | GET `search?q=` or a nonsense query | `{results: []}` | ✅ `test_empty_query_returns_no_results`, `test_no_match_returns_empty` |
| 2d.10 | Tickler/covenant-driven widgets | — | — | **Not built** -- no reminder/scheduling system, no covenant/DSCR data model. Explicit scope decision, not a gap | 🔲 Deferred (scope decision) |

---

## Step 3 — The Secure Request Email ✅ Built (logged, not delivered)

Copy requirement: *"authenticated (SPF / DKIM / DMARC)... listing exactly
what's needed, with one action: log in and upload."*

**Scope decision (explicit, not silently faked):** no real mail provider
(SMTP/SendGrid/etc.) is wired up. "Sending" composes the exact email content
and persists it as an append-only `RequestEmail` row (visible via admin, the
API, and the dashboard's "View email" modal) plus an INFO-level console log
line -- it is never actually delivered. SPF/DKIM/DMARC (3.1) and no-reply
bounce handling (3.7) are therefore not applicable until a real provider is
chosen; those rows stay 🔲 until that decision is made (see `CLAUDE.md`).

Backend: `document_requests/email_service.py` + `checklist.py`, tests in
`backend/document_requests/tests.py` (`RequestEmailTests`).
Frontend: `EmailPreviewModal` in `app/dashboard/page.tsx`.

**v3 update:** the doclist now lists whichever Lender items were actually
selected for the request (via Step 2b), not a fixed 5-item list -- Loan
Admin items never appear (see 2b.9). Copy also changed to "...for this
cycle" per the v3 mockup.

| ID | Case | Given | When | Then | Status |
|----|------|-------|------|------|--------|
| 3.1 | Email sends from a verified/authenticated domain | — | — | **N/A until a real provider is chosen** -- SPF/DKIM/DMARC don't apply to a logged-only email | 🔲 Planned (blocked on provider decision) |
| 3.2 | Checklist in the email matches the request | — | Send a request | Body contains every item in `DEFAULT_CHECKLIST`, count matches "Required documents · N" | ✅ `test_logged_email_body_includes_every_checklist_item` |
| 3.2b | Checklist is currently fixed, not per-request | — | — | Same 5 items on every request -- Step 2's form has no checklist picker yet, so this is honestly a known simplification, not a bug | 🔲 Planned (make configurable once Step 2 grows a picker) |
| 3.3 | Body includes borrower + company name | — | Send a request | Both strings present verbatim in `body_text` | ✅ `test_logged_email_body_includes_borrower_and_company_name` |
| 3.3b | Upload link is single-purpose | — | Send a request | Body's upload URL embeds this request's unique `link_token` | ✅ `test_logged_email_body_includes_the_upload_link_token` — note: the URL doesn't resolve to anything yet, Step 4 isn't built |
| 3.4 | Link expiry enforced | — | — | Depends on Step 4 (the actual upload portal) to enforce; the email's stated expiry date is correct (2.6/2.17 already assert `linkExpiresAt`), but nothing server-side rejects a used-past-expiry link yet since there's no portal to reject at | 🔲 Planned (Step 4 dependency) |
| 3.5 | Expiry shown matches send date + 7 days | — | Send a request | `RequestEmail.body_text` expiry line matches `DocumentRequest.link_expires_at` exactly | ✅ `test_logged_email_expiry_date_matches_link_expires_at` |
| 3.6 | Anti-phishing footer present | — | Send a request | Body contains "Freedom Bank will never ask for your password or one-time codes by email" | ✅ `test_logged_email_includes_anti_phishing_footer` |
| 3.7 | No-reply / bounce handling | — | — | **N/A until a real provider is chosen** (see scope decision above) | 🔲 Planned (blocked on provider decision) |
| 3.8 | Resend logs a fresh email with the new token | — | Send, then resend | A second `RequestEmail` row exists, its body contains the *new* `link_token`, not the old one | ✅ `test_resend_logs_a_second_email` + `test_get_latest_email_returns_the_most_recent_one` |
| 3.9 | Sending always logs exactly one email | — | POST `action=send` | `RequestEmail.objects.count() == 1` | ✅ `test_sending_a_request_logs_exactly_one_email` |
| 3.10 | Draft never logs an email | — | POST `action=draft` | `RequestEmail.objects.count() == 0` | ✅ `test_draft_does_not_log_an_email` |
| 3.11 | Email addressed to the applicant | — | Send a request | `to_email` == the form's email field, `from_email` == `requests@freedombankva.com` | ✅ `test_logged_email_goes_to_the_applicants_address` |
| 3.12 | Subject matches mockup copy exactly | — | Send a request | `"Documents needed to begin your loan application"` | ✅ `test_logged_email_subject_matches_mockup_copy` |
| 3.13 | `GET /api/requests/<id>/email` returns the latest | Sent + resent once | GET the email endpoint | Body reflects the *second* (latest) email's token, not the first | ✅ `test_get_latest_email_returns_the_most_recent_one` |
| 3.14 | 404 when nothing logged yet | Draft with no send | GET the email endpoint | 404 | ✅ `test_get_email_404s_when_none_logged_yet` |
| 3.15 | Email endpoint requires auth | Not logged in | GET the email endpoint | 403 | ✅ `test_get_email_requires_authentication` |
| 3.16 | `RequestEmail` is read-only in admin | — | Inspect `RequestEmailAdmin` | No add/change permission — same append-only pattern as `LoginEvent` | ✅ `test_request_email_is_read_only_via_admin` |
| 3.17 | Console log line appears on send | — | Send a request, check gunicorn output | INFO line: `Secure request email logged (not actually sent...)` with request id, recipient, subject | ✅ verified manually this session (required adding a `LOGGING` config to `settings.py` — Django doesn't wire app-logger output to console by default) |
| 3.18 | "View email" modal renders the logged content | Frontend | Click "View email" on a sent/expired/uploads_complete row | Modal shows From/To/Subject + the full body, with a note that it wasn't actually delivered | 🟡 |
| 3.19 | "View email" absent on drafts | Frontend | Draft row in Recent requests | No "View email" button (nothing has been logged yet) | 🟡 |

---

## Step 4 — Customer Upload Portal ✅ Built

Copy requirement: *"one checklist row per document... temporary parking bay...
session runs on the timer... suspicious activity ends it immediately."*

**Scope decisions (explicit, not silently faked):**
- Documents are written to **disk** under `UPLOAD_STORAGE_ROOT` (same choice
  as appstore's `credit_file_server` usecase), organized
  `{company} (req{id})/{checklist item}/{upload_id}_{filename}`.
- Checklist items are instantiated from Step 3's fixed `DEFAULT_CHECKLIST` at
  send time (still not per-request configurable — same known simplification
  noted in Step 3).
- Session window is **20 minutes** (a ballpark from the mockup's "14:32
  session remaining", not derived from any real spec).
- The fraud/session guard is **two simple, deterministic heuristics** --
  `failed_attempts >= 5` ("repeated failed upload attempts") and
  `total_attempts >= 20` ("unusually high upload volume") -- explicitly
  **not** real bot/automation detection. **Location-jump detection (4.8) is
  NOT implemented at all** -- it would need real IP geolocation
  infrastructure this project doesn't have. That row stays 🔲 until a
  decision is made to add it.
- A fraud trip logs an alert email to the banker via the same
  `RequestEmail` log-only mechanism as Step 3 (no real notification system).

Backend: `document_requests/storage.py` (disk I/O), models `ChecklistItem` /
`UploadedFile` / `UploadSession`, views in `document_requests/views.py`
(`upload_info_view`, `upload_document_view`, plus banker-side
`uploaded_files_view` / `serve_uploaded_file_view`). Tests in
`UploadPortalTests` and `BankerFileAccessTests`
(`backend/document_requests/tests.py`).
Frontend: `app/upload/[token]/page.tsx`; dashboard gained "Copy link" and a
real "View docs" modal (`FilesModal`).

**v3 update:** the portal now shows only Lender items (never Loan Admin,
see 2b.9), grouped by category with a header per group, matching the
mockup's `cgroup` sections.

| ID | Case | Given | When | Then | Status |
|----|------|-------|------|------|--------|
| 4.1 | Checklist reflects exactly the requested documents | Request sent | GET `/api/upload/<token>` | 5 items, names match `DEFAULT_CHECKLIST` exactly, in order | ✅ `test_checklist_items_created_at_send_time` |
| 4.1b | Info endpoint starts the session timer | First open | GET `/api/upload/<token>` | `sessionSecondsRemaining` is set, `UploadSession.started_at` is now set | ✅ `test_info_endpoint_returns_checklist_and_starts_session_timer` |
| 4.1c | Invalid token | — | GET a bogus token | 410 | ✅ `test_info_endpoint_invalid_token_returns_410` |
| 4.2 | Per-row upload progress (live %) | — | — | **Not implemented** -- would need chunked/resumable upload; current uploads are single-shot multipart, no progress events | 🔲 Planned |
| 4.3 | Completed row shows metadata | Upload succeeds | GET info | Item shows `fileName`; banker's `GET /uploads` shows size + timestamp too | ✅ `test_upload_success_marks_item_uploaded`, `test_list_uploaded_files_shows_the_upload` |
| 4.4 | Uploaded file lands in parking bay, not the credit file | — | Upload | `UploadedFile` row created, no "review"/"approved" concept exists yet (Step 6 not built) -- it's parking-bay-only by construction | ✅ implicit in `test_upload_success_marks_item_uploaded` |
| 4.4b | File actually lands on disk correctly | — | Upload | Exact byte content readable back from `storage.absolute_path(...)` | ✅ `test_upload_writes_file_to_disk` — also verified live via curl (real file, correct folder structure) |
| 4.5 | Session timer counts down | Frontend | Load the portal | Countdown chip ticks down client-side, resyncs from server on load/upload | 🟡 |
| 4.6 | Session expiry blocks further upload, prior uploads preserved | Session started >20 min ago | POST upload | 410, checklist item stays `pending` (rejected before any file write) | ✅ `test_session_expiry_blocks_further_upload` |
| 4.7 | Fraud guard — high upload volume ("automated tooling") | 20 upload attempts | POST uploads | `status` -> `fraud_stopped`, reason mentions "automated" | ✅ `test_high_volume_of_attempts_trips_fraud_as_automated_activity` |
| 4.8 | Fraud guard — location jump | — | — | **NOT implemented** -- needs real IP geolocation, explicitly out of scope for now | 🔲 Planned (infra dependency) |
| 4.9 | Fraud guard — repeated failed uploads | 5 failed attempts (no file) | POST uploads | `status` -> `fraud_stopped`, reason "Repeated failed upload attempts" | ✅ `test_repeated_failed_uploads_trip_fraud_guard` |
| 4.10 | Fraud trip preserves prior uploads | One real upload, then trip fraud | — | That checklist item still shows `uploaded` with its file intact | ✅ `test_fraud_trip_preserves_already_uploaded_files` |
| 4.10b | Fraud trip blocks further uploads | Fraud already tripped | POST another upload | 410 | ✅ `test_fraud_trip_blocks_further_uploads` |
| 4.11 | Fraud trip notifies the relationship manager | Fraud trips | — | `RequestEmail(kind='fraud_alert')` logged, addressed to `created_by.email`, names the reason | ✅ `test_fraud_trip_logs_an_alert_email_to_the_banker` — also verified live (real alert body content) |
| 4.12 | File size limit enforced | File over the cap | POST upload | 400, counts as a failed attempt | ✅ `test_oversized_file_rejected` (cap temporarily lowered in-test to avoid allocating 20MB+ per run) |
| 4.12b | File type restrictions | — | — | **Not implemented** -- no MIME/extension allowlist exists; any file type is currently accepted | 🔲 Planned (no requirement specified which types to block) |
| 4.13 | Re-upload replaces, doesn't duplicate the checklist row | Item already uploaded | Upload again | `ChecklistItem.current_file` points to the new file; old `UploadedFile` row (and disk file) kept for history, not deleted | ✅ `test_reupload_replaces_current_file_keeps_old_row` |
| 4.14 | All items uploaded -> request marked complete | Upload every item | — | `DocumentRequest.status` -> `uploads_complete`; further uploads to a complete request aren't blocked by a specific check but there's nothing pending left to replace | ✅ `test_all_items_uploaded_marks_request_uploads_complete`, `test_partial_upload_keeps_request_sent` |
| 4.15 | Expired link (7-day link, not the 20-min session) blocks upload | `link_expires_at` in the past | GET info | 410, status flips to `expired` | ✅ `test_expired_link_blocks_upload_and_flips_status` |
| 4.16 | Resend resets the session but keeps checklist progress | One item already uploaded | Banker resends | `UploadSession` deleted (fresh timer on next open); checklist item's `uploaded` status untouched | ✅ `test_resend_resets_session_but_keeps_checklist_progress` |
| 4.17 | Banker file list requires auth | Not logged in | GET `/api/requests/<id>/uploads` | 403 | ✅ `test_list_uploaded_files_requires_auth` |
| 4.18 | Banker can serve/download a specific file | — | GET the serve endpoint | 200, exact original bytes | ✅ `test_serve_uploaded_file_returns_original_bytes` |
| 4.19 | Serving a nonexistent file 404s | — | GET serve with a bogus id | 404 | ✅ `test_serve_nonexistent_file_404s` |
| 4.20 | Dashboard metrics become real (no longer null) | Files uploaded, one fraud-stopped | GET `/api/requests` | `docsInParkingBay` and `sessionsEndedFraud` are real counts | ✅ `test_parking_bay_and_fraud_metrics_are_now_real` — also verified live |
| 4.21 | "Awaiting customer" excludes requests with any upload | 2 sent, 1 has an upload | GET `/api/requests` | `activeRequests=2`, `awaitingCustomer=1` | ✅ `test_awaiting_customer_excludes_requests_with_any_upload` |
| 4.22 | Upload link in the Step 3 email is now real | Send a request | Open the link from the logged email | Resolves to the actual `/upload/<token>` portal instead of the mockup's fake `upload.freedombankva.com` domain | ✅ verified live (link composed with `settings.FRONTEND_BASE_URL`) |
| 4.23 | **Test-isolation regression guard** | — | Run the test suite twice | The real `UPLOAD_STORAGE_ROOT` directory stays empty afterward -- Django's `TestCase` only sandboxes the DB (rolled back per test), NOT disk writes, so without an explicit `override_settings` to a temp dir, every test run would leave real files behind (this actually happened once during development; fixed via module-level `setUpModule`/`tearDownModule`) | ✅ verified manually this session |
| 4.24 | "Copy link" / "View docs" dashboard actions | Frontend, sent request | Click Copy link / View docs | Clipboard gets the real working `/upload/<token>` URL; modal lists uploaded files with working view/download links | 🟡 |
| 4.25 | Upload portal terminal states render correctly | Frontend | Load an expired/fraud-stopped/complete link | Correct icon + message per state, no raw error dump | 🟡 |

---

## Step 5 — Session Terminal States ✅ Built

Copy requirement: *"Completion thanks the customer and triggers an automatic
confirmation email from the platform... Reference REQ-2026-0847."*

**Scope decisions (explicit, not silently faked):**
- 5.3/5.4/5.5 (fraud termination screen, logging+alerting, link deactivation)
  turned out to already be fully satisfied by Step 4's own fraud-guard work
  (`_trip_fraud_if_needed`, `log_fraud_alert_email`, the 410 block on further
  uploads) — nothing new to build there, just re-verified and cross-referenced
  below instead of duplicating tests.
- The genuinely new work this step: `DocumentRequest.reference_number`
  (`REQ-{year}-{id:04d}`, assigned once at first send, stable across resends,
  unique by construction since it's derived from the row's own unique id —
  not a separate per-year counter table) and `log_completion_confirmation_email`
  (Step 3/4's same log-only `RequestEmail` mechanism, `kind='confirmation'`,
  fired exactly once when the last checklist item completes).

Backend: `DocumentRequest.reference_number` field (migration `0004`),
`RequestEmail.KIND_CHOICES` gained `'confirmation'`, `_assign_reference_number`
+ `log_completion_confirmation_email` in `document_requests/views.py` /
`email_service.py`. Tests in `ReferenceNumberAndConfirmationEmailTests`
(`backend/document_requests/tests.py`).
Frontend: `app/upload/[token]/page.tsx`'s "Thanks for uploading" screen now
shows the reference number and a "Confirmation email sent to {email} from the
platform" line; `app/dashboard/page.tsx`'s Recent Requests row shows
"· Reference REQ-2026-####" next to the borrower/company name.

**v3 update:** copy changed from "All five documents..." to "All requested
documents..." since the checklist size is now variable per request (Step 2b).

| ID | Case | Given | When | Then | Status |
|----|------|------|------|------|--------|
| 5.1 | All-documents-uploaded completion, reference number shown | Last checklist item uploads | — | `status` -> `uploads_complete`; `referenceNumber` non-null in both `upload_info_view` and the requests list | ✅ `test_all_items_uploaded_marks_request_uploads_complete` (Step 4), `test_reference_number_included_in_upload_info`, `test_reference_number_included_in_list_response` — also verified live via curl (real upload sequence -> real reference number) |
| 5.2 | Completion triggers confirmation email | Last item uploads | — | Exactly one `RequestEmail(kind='confirmation')` logged, addressed to the customer, subject/body match mockup copy, includes the reference number | ✅ `test_completion_logs_confirmation_email_exactly_once`, `test_confirmation_email_addressed_to_borrower_with_reference` — also verified live (real logged email content) |
| 5.2b | Confirmation email doesn't fire early | Only some items uploaded | — | No `kind='confirmation'` row exists yet | ✅ `test_confirmation_email_not_logged_on_partial_upload` |
| 5.2c | Confirmation email doesn't refire on post-completion re-upload | Request already `uploads_complete` | Customer replaces an already-uploaded file | Still exactly one `kind='confirmation'` row — no duplicate | ✅ `test_confirmation_email_not_relogged_on_reupload_after_completion` |
| 5.3 | Fraud-guard termination screen | A Step 4 guard trip | Customer reopens the link | Frontend renders the fraud-stopped terminal state, not the success screen (same `_resolve_active_request` branch as Step 4) | ✅ covered by Step 4's `test_repeated_failed_uploads_trip_fraud_guard` / `test_high_volume_of_attempts_trips_fraud_as_automated_activity` — no new test needed, same mechanism |
| 5.4 | Fraud termination logs + alerts | Guard trips | — | Event logged (`UploadSession.fraud_reason`/`fraud_flagged_at`) and banker alerted (`RequestEmail(kind='fraud_alert')`) both actually happen, not just copy | ✅ Step 4's `test_fraud_trip_logs_an_alert_email_to_the_banker` |
| 5.5 | Link deactivation after fraud stop | Guard already tripped | POST/GET the same link again | 410, no further upload possible | ✅ Step 4's `test_fraud_trip_blocks_further_uploads` |
| 5.6 | Reference number uniqueness | Two different requests sent | — | `reference_number` differs between them, never reused | ✅ `test_reference_number_unique_per_request` |
| 5.6b | Reference number stable across resend | Request already has a reference number | Banker resends | Reference number unchanged (unlike `link_token`, which rotates) | ✅ `test_reference_number_stable_across_resend` |
| 5.6c | Draft has no reference number yet | Draft, never sent | — | `referenceNumber` is `null` — assigned only at first send | ✅ `test_draft_has_no_reference_number` |

---

## Step 6 — Parking Bay Review & Review Summary ✅ Built

Copy requirement: *"No emails fire from here... one secure email and one
extraction kick-start close out the whole request."*

**Scope decisions (explicit, not silently faked):**
- Review fields (`review_status`/`review_comment`/`reviewed_at`/`reviewed_by`)
  live on `UploadedFile`, not `ChecklistItem` -- so a re-upload after a flag
  naturally starts a fresh `pending` review on the new row while the old
  flagged row (and its comment) stays in history untouched (6.11), with no
  extra bookkeeping needed.
- `DocumentRequest.extraction_queued_at` is a real, one-time timestamp set by
  "Kick-start extraction" (blocked from firing twice) -- but **Step 7 (the
  actual twin-extraction pipeline) is not built yet**, so nothing consumes
  this field yet. It's a real gate + real record of the decision, honestly
  scoped to stop short of a pipeline that doesn't exist.
- The document *preview* is real where the browser can render it natively --
  `<img>` for `image/*`, `<iframe>` for `application/pdf` -- and an honest
  "no inline preview for this file type, open/download instead" fallback for
  everything else (xlsx, docx, etc.), rather than faking a universal
  document viewer.
- Every accepted document is presumed extraction-eligible; there's no
  per-document-type extraction rule yet since Step 7 doesn't exist to have
  rules for.

Backend: `UploadedFile` gained the four review fields (migration `0005`),
`RequestEmail.KIND_CHOICES` gained `'review_flags'`,
`log_review_flags_email` in `email_service.py`. New endpoints (all
banker-authenticated) in `document_requests/views.py`: `GET
/api/requests/<id>/parking-bay`, `POST .../parking-bay/<item_id>/review`,
`POST .../parking-bay/send-flags-email`, `POST
.../parking-bay/kick-start-extraction`. Tests in `ParkingBayReviewTests`
(`backend/document_requests/tests.py`, 17 tests, 106 total across the whole
backend).
Frontend: new `app/parking-bay/[id]/page.tsx` (file list sidebar + preview/
review panel + review-summary table + the two batch actions); dashboard
gained a "Review" button on any request with uploads.

**v3 update:** Loan Admin items are excluded from this screen entirely (see
2b.12) -- the parking bay only ever lists Lender items, since only those
have an upload mechanism. A new `LoanStatusStepper` (Request → Documents →
Extraction → Credit review → Term sheet → Decision → Commitment → Signed →
Processing) was added -- a real "you are here" indicator over state this
project actually tracks (`extraction_queued_at`), not a fake live tracker
for the macro-pipeline steps beyond Extraction, which aren't built.

| ID | Case | Given | When | Then | Status |
|----|------|-------|------|------|--------|
| 6.1 | Parking bay lists exactly the uploaded files | 5 items uploaded | GET `/api/requests/<id>/parking-bay` | 5 items returned, each with its current file attached | ✅ `test_parking_bay_lists_exactly_the_uploaded_files` — also verified live via curl |
| 6.1b | Parking bay requires auth / 404s for a bad id | — | GET as anon / bogus id | 403 / 404 | ✅ `test_parking_bay_requires_auth`, `test_parking_bay_404s_for_nonexistent_request` |
| 6.2 | Per-file status indicators | Mixed decisions | GET parking bay | Each file's `reviewStatus` is exactly one of `pending`/`approved`/`flagged`, rendered as distinct badges | ✅ `test_review_summary_reflects_live_decisions` — also verified live (4 approved, 1 flagged, badges rendered correctly) |
| 6.3 | "Submit for extraction" on one file doesn't email anyone | Approve a file | — | No `RequestEmail` of any kind logged by the per-file decision itself | ✅ `test_submit_for_extraction_does_not_send_any_email` |
| 6.3b | Reviewing an item with no upload is rejected | Checklist item exists but nothing uploaded to it | POST review | 400 | ✅ `test_cannot_review_an_item_with_no_upload` |
| 6.3c | Decision must be approve or flag | — | POST review with `decision: "maybe"` | 400 | ✅ `test_review_requires_a_valid_decision` |
| 6.4 | "Flag — needs re-upload" requires a comment | — | POST `decision: "flag"`, no comment | 400, file stays `pending` | ✅ `test_flag_without_comment_is_rejected` |
| 6.4b | Flag with a comment is recorded | — | POST `decision: "flag"` with comment | `reviewStatus` -> `flagged`, comment saved verbatim | ✅ `test_flag_with_comment_is_recorded` |
| 6.5 / 6.10 | Flagged file excluded from extraction batch; kick-start only queues approved files | 4 approved, 1 flagged | POST kick-start-extraction | `queuedCount` == 4 (flagged one excluded) | ✅ `test_kick_start_queues_only_approved_files` — also verified live (curl: 4 queued of 5) |
| 6.6 | Review summary reflects live decisions | Decisions change mid-review | GET parking bay again | `approvedCount`/`flaggedCount`/`reviewComplete` always match current state, no stale cache | ✅ `test_review_summary_reflects_live_decisions`, `test_review_complete_once_every_item_has_a_decision` |
| 6.7 | Batch email fires exactly once per request, bundles all flags | 2 flagged items | POST send-flags-email | Exactly one `RequestEmail(kind='review_flags')`, body contains both comments (not two separate emails) | ✅ `test_send_flags_email_bundles_all_flags_into_one_email` — also verified live (real logged email content) |
| 6.8 | Batch email blocked with zero flags | Nothing flagged | POST send-flags-email | 400 -- backend refuses to log an empty batch (frontend also hides the button when `flaggedCount === 0`) | ✅ `test_send_flags_email_requires_at_least_one_flag` |
| 6.9 | Extraction kick-start disabled until review complete | Only 1 of 5 reviewed | POST kick-start-extraction | 400, `extraction_queued_at` stays null | ✅ `test_kick_start_blocked_until_review_complete` |
| 6.9b | Extraction can't be queued twice | Already queued | POST kick-start-extraction again | 400 | ✅ `test_kick_start_cannot_be_queued_twice` — also verified live |
| 6.11 | Re-requested document re-enters the parking bay on re-upload | Item flagged | Customer re-uploads to the same checklist item | New `UploadedFile` row, `reviewStatus` back to `pending`; the old flagged row (and its comment) untouched | ✅ `test_flagged_document_re_enters_parking_bay_on_reupload` |
| 6.12 | Document preview renders for images/PDFs, honest fallback otherwise | — | Frontend, open a file in the review panel | `image/*` -> `<img>`, `application/pdf` -> `<iframe>`, anything else -> "no inline preview" + download link | 🟡 (real for the two implemented types; not independently automated) |
| 6.13 | Dashboard surfaces a flagged item, not just `status` | Request is `uploads_complete` (every item has a file) but one file is flagged | GET `/api/requests` | `hasFlaggedItems: true` on that row -- `status` alone can't show this, since every Lender item still has *a* file | ✅ `test_dashboard_list_flags_a_request_with_a_flagged_item` — also verified live against a real request (`REQ-2026-0009`) that had a flagged item silently hidden by the "Uploads complete" badge before this fix |
| 6.13b | Flag clears once the item is re-uploaded | Flagged item, then customer replaces it | GET `/api/requests` | `hasFlaggedItems` back to `false` -- the fresh (pending-review) file supersedes the flagged one | ✅ `test_dashboard_flag_clears_once_the_item_is_reuploaded` |

---

## Step 7 — Twin Extraction (live pipeline) ✅ Built (real content extraction — see scope decisions)

**Scope decision #1, made explicitly with the user before building this
step:** there is no real OCR/AI extraction service in this project. Two
options were presented -- (a) a real pipeline with heuristic content-based
extraction, or (b) a real DB-backed stage machine with no content reading at
all, placeholder extracted values. **Option (b) was built first.**

**Scope decision #2, made explicitly with the user while starting Step 8:**
Step 8's mockup needs real per-value data (dollar amounts, confidence,
source) to review, which option (b) can't produce. Presented the choice
again -- rescope Step 8 around twin-level handoff only, or go back and
upgrade Step 7 to real content extraction. **The user chose to upgrade
Step 7.** So, as of this step:
- Stage progression (`DocumentTwin`/`BusinessTwin`, migration `0006`) is
  real: real rows, real timestamps, real one-stage-at-a-time advancement via
  an explicit POST (the server always moves to exactly
  `STAGE_ORDER[current_index + 1]`, so skipping/reordering is structurally
  impossible, not just discouraged).
- "Classified" is still a simple deterministic lookup (`extraction.py`'s
  `classify()`) keyed by checklist item name, not file content -- there's no
  real document-type classifier, and that's an honest, documented
  simplification, not upgraded in this pass.
- "Extracted" (migration `0007`, `content_extraction.py`) is now **real**:
  it reads the actual uploaded bytes and extracts real values using real
  libraries already available in this environment -- `pdfplumber` (PDF text),
  `python-docx` (docx paragraphs), `openpyxl` (direct spreadsheet cell
  reads), `pytesseract`+Tesseract (image OCR), plain UTF-8 decode for
  `.txt`. Dollar amounts / percentages / ratios / dates are found via real
  regex over that genuinely-extracted text; spreadsheet cells are read
  directly (no regex needed, no ambiguity) and get full 1.0 confidence.
  There is still **no real NLP/AI** -- this is honest pattern-matching over
  real content, not semantic field understanding (it can't tell "Total
  revenue" from "Total expenses"; it just finds dollar-shaped numbers).
  Unsupported file types (zip, unknown binary) get zero values, not fake
  ones. Confidence is a real but simple deterministic heuristic per
  extraction method (documented in `content_extraction.py`'s docstring), not
  a trained model's score.
- "Provenance" and "Confidence" stages are now real aggregates over the
  `ExtractedValue` rows created at "Extracted" (source-pointer count,
  average confidence, HITL-review count at the `CONFIDENCE_ROUTING_THRESHOLD
  = 0.85` cutoff) -- not placeholder strings anymore.
- Business twin's Relationship/Entities stages are real progression but
  carry no real entity graph; Covenant ledger/Indicators/Allocation are
  really gated on document-twin completion (see 7.2) but have no real
  covenant/obligation data model behind them yet -- that part of the scope
  choice is unchanged.

Backend: `DocumentTwin`, `BusinessTwin`, `ExtractionEvent`, `ExtractedValue`
models; `document_requests/extraction.py` (classification lookup) and
`content_extraction.py` (real content extraction, new dependencies added to
`requirements.txt`: pdfplumber, python-docx, openpyxl, pytesseract, pillow).
Endpoints unchanged from the first pass: `GET /api/requests/<id>/extraction`,
`POST .../extraction/<twin_id>/advance`, `POST .../business-twin/advance`.
Tests in `TwinExtractionTests` (16), `ContentExtractionUnitTests` (9),
`ExtractedValueModelTests` (1), `DocumentTwinContentExtractionAPITests` (5)
-- 31 Step-7 tests total, 137 across the whole backend.
Frontend: `app/extraction/[id]/page.tsx` gained a real extracted-values
table (field/value/source/confidence/status) once a twin reaches `extracted`
or later.

| ID | Case | Given | When | Then | Status |
|----|------|-------|------|------|--------|
| 7.1 | Document twin stage sequence enforced | Twin at `received` | POST advance repeatedly | Moves `classified` -> `extracted` -> `provenance` -> `confidence` in strict order; 400 once already at `confidence` | ✅ `test_document_twin_stage_sequence_enforced` — also verified live via curl |
| 7.1b | Classification label is real, derived from the checklist item | Twin for the "bank statements" item | Advance to `classified` | `classificationLabel` == `"Bank statement"` | ✅ `test_classification_label_derived_from_checklist_item_name` — also verified live |
| 7.2 | Business twin waits on document twin | Not every twin has reached `extracted` | POST business-twin advance past `entities` | 400 -- blocked until every document twin in the request is at `extracted` or later | ✅ `test_business_twin_covenant_ledger_blocked_until_all_twins_extracted`, `test_business_twin_covenant_ledger_still_blocked_if_only_some_twins_extracted`, `test_business_twin_covenant_ledger_unlocks_once_all_twins_extracted` — also verified live (5-document request, gate opens only once all 5 reach `extracted`) |
| 7.2b | Relationship/Entities need no gate | Fresh business twin | POST advance | `relationship` -> `entities` succeeds immediately, no document-twin dependency | ✅ `test_business_twin_relationship_and_entities_start_immediately` |
| 7.3 | Overall progress % is a real aggregate | Document twin at 3/5 stages, business twin at 2/5 | GET extraction | `overallPercent` == average(60%, 40%) == 50 -- computed, not decorative | ✅ `test_overall_percent_is_a_real_aggregate` |
| 7.4 | Live log entries append in chronological order | Several advances | GET extraction | `log` timestamps strictly non-decreasing | ✅ `test_log_entries_in_chronological_order` |
| 7.5 | Every extraction step writes an audit event | Any advance | — | Stage event + matching `audit.write` event both logged | ✅ `test_every_stage_transition_writes_audit_events` |
| 7.6 | Low-confidence values route to HITL review | Values with confidence < 0.85 | Advance to `confidence` | `ExtractedValue.needs_review` is `True` below the threshold, `False` at/above it; the `confidence` stage's detail reports the real count | ✅ `test_needs_review_below_threshold`, `test_confidence_stage_reports_real_average_and_review_count` |
| 7.7 | Extraction failure handling | A corrupt/unreadable PDF | Advance to `extracted` | 400 with the real parser error message; stage stays at `classified` (not advanced); `extract.failed` event logged; retriable (a valid file at the same path succeeds on the next advance) | ✅ `test_corrupt_pdf_extraction_failure_does_not_advance_stage`, `test_extraction_can_be_retried_after_a_failure`, `test_pdf_corrupt_file_raises_extraction_failed` — also verified live via curl (real garbage-bytes PDF, real pdfplumber error surfaced) |
| 7.8 | Concurrent extractions don't cross-contaminate | Two separate requests, both queued | Advance one request's twin | The other request's twins/business twin are completely untouched | ✅ `test_concurrent_extractions_do_not_cross_contaminate` |
| 7.9 | Only approved files get a document twin | 4 approved, 1 flagged | Kick-start extraction | Exactly 4 `DocumentTwin` rows created, none for the flagged file | ✅ `test_kick_start_creates_a_twin_per_approved_file_only` |
| 7.10 | Extraction view requires extraction to be queued first | Request never kicked off | GET extraction | 400 | ✅ `test_extraction_view_400s_before_kickoff` |
| 7.11 | Real dollar/percentage/ratio/date extraction from real text | `.txt` file with real financial-looking text | Advance to `extracted` | Regex matches are genuine (real value, real line number, correct confidence per pattern) | ✅ `test_text_plain_dollar_amount`, `test_text_plain_percentage_and_ratio`, `test_real_dollar_amount_extracted_from_text_file` — also verified live |
| 7.12 | Real PDF text extraction | A real PDF (built with reportlab) containing `$4,218,400` and `1.14x` | Advance to `extracted` | Both values found with the correct page number as source | ✅ `test_pdf_real_extraction` — also verified live via curl with a real generated PDF |
| 7.13 | Real spreadsheet cell extraction | A real `.xlsx` with numeric cells | Advance to `extracted` | Direct cell values extracted (no regex), confidence == 1.0, source cites the real sheet name + cell coordinate | ✅ `test_xlsx_direct_cell_read_full_confidence` — also verified live via curl with a real generated `.xlsx` |
| 7.14 | Real docx paragraph extraction | A real `.docx` with a dollar amount | Advance to `extracted` | Value found with the correct paragraph number as source | ✅ `test_docx_real_extraction` |
| 7.15 | Unsupported file types don't crash or fake results | e.g. `application/zip` | Advance to `extracted` | Zero values, no exception -- honest empty result | ✅ `test_unsupported_file_type_returns_empty_without_error`, `test_no_extractable_values_advances_cleanly` |
| 7.16 | Extracted-value volume is capped | 100 regex-matchable lines | Extract | Result capped at `MAX_VALUES_PER_DOCUMENT` (30), not unbounded | ✅ `test_max_values_per_document_cap` |
| 7.17 | Image OCR extraction | `image/*` file | Advance to `extracted` | OCR'd text is regex-scanned with a real confidence discount vs. direct text | 🟡 (real code path via `pytesseract`, not independently automated -- OCR accuracy on a synthetic test image would be flaky; same "not independently automated" pattern as 4.5/6.12) |

---

## Step 8 — Extraction Review & Handoff + Business Twin 🔲 Planned

Copy requirement: *"Clean result → submit to loan officer. A discrepancy →
HITL comment goes back to the customer... obligation stays open until
resolved."*

| ID | Case | Expected |
|----|------|----------|
| 8.1 | Confidence threshold routes to HITL correctly | Fields below the confidence cutoff (e.g. 71%, 68% in the mock) are flagged "HITL review"; fields above (97%+) show "Verified" |
| 8.2 | Every value shows source + confidence | No extracted field is missing its `page.row`/sheet-cell provenance pointer |
| 8.3 | "Submit for loan officer review" only enabled when zero HITL items remain | Button blocked/hidden while any field is still `HITL review` status |
| 8.4 | Discrepancy path requires a comment | "Send secure email with review comments" blocked on an empty textarea |
| 8.5 | Discrepancy email is sent verbatim | The exact HITL comment text appears in the customer-facing email body, unmodified |
| 8.6 | Discrepancy keeps the obligation open | After sending, the covenant/document obligation is *not* marked fulfilled until a corrected upload is verified |
| 8.7 | Document twin version increments on re-upload | A corrected re-upload produces "v2 of 2" (or higher), not an overwrite of v1's history |
| 8.8 | Business twin updates only from a *verified* document twin | An unverified/HITL-pending document twin does not push values into the business twin yet |
| 8.9 | Advisory flag on covenant breach | DSCR (or any monitored ratio) crossing its floor/ceiling produces an advisory flag — and explicitly takes **no automatic action** (per copy: "the system takes no action on its own") |
| 8.10 | Advisory flag shows full basis | Flag includes the calculation (numerator, denominator, source document, sheet/row) — not just a bare "flagged" badge |
| 8.11 | Consolidated allocation closes multiple obligations from one upload | One financial statement upload satisfies the stated obligation for all three linked entities simultaneously — verify all three covenant rows flip to "Fulfilled" |
| 8.12 | Every twin update is audit-logged | "actor, source document, timestamp" recorded for each mutation — matches the append-only pattern from Step 1's `LoginEvent` |
| 8.13 | Loan history table is read-only | Prior approaches (approved/withdrawn/declined) cannot be edited from this screen — historical record only |
| 8.14 | Declined-history reasoning preserved verbatim | A 2019 decline reason (e.g. "DSCR 1.05x below policy floor") remains exactly reconstructable years later, no data loss |

---

## Step 9 — Customer Activity Log 🔲 Planned

Copy requirement: *"every event is typed — bank action, customer action,
system, or alert."*

| ID | Case | Expected |
|----|------|----------|
| 9.1 | Every event carries exactly one correct type | Each trail entry is tagged bank / customer / system / alert and matches who/what actually triggered it |
| 9.2 | Trail entries are strictly chronological per customer | Dates never appear out of order within one customer's trail |
| 9.3 | Multiple concurrent customers don't cross-contaminate | Events for Priya Sharma never appear under Marcus Lee's trail or vice versa |
| 9.4 | Fraud-stopped customer shows the alert event distinctly | Rohan Patel's "Automation signals detected" renders as an `alert`-typed event, visually distinct from routine bank/customer/system events |
| 9.5 | Expired-then-resent trail preserves both events | Elena Ortiz's log keeps *both* "Link expired" and "Request resent by banker" as separate entries — resend doesn't erase the expiry event |
| 9.6 | Status badge matches the latest trail event | The header badge (e.g. "Twin extraction · 78%", "With loan officer", "Resent · awaiting customer", "Session ended — fraud guard") always reflects the true current state, not a stale one |
| 9.7 | "Open"/"View package"/"Nudge again" actions match state | Action button offered is contextually correct for that customer's current status (e.g. "Nudge again" only for awaiting-customer state) |
| 9.8 | Full lineage survives the whole pipeline | A single request's trail includes every step it passed through: send → email open → upload → review → extraction → (HITL if any) → handoff — nothing silently dropped from the log |

---

## Cross-cutting / non-functional 🔲 Planned

| ID | Case | Expected |
|----|------|----------|
| X.1 | All secure links are single-purpose | No upload/session link from Step 3/4 works for any request other than the one it was issued for |
| X.2 | All bank-to-customer emails are DKIM/SPF-passing | Steps 3, 6, 8 emails all originate from an authenticated sending domain |
| X.3 | No plaintext credentials/tokens in logs | Audit trail (`LoginEvent`, extraction log, activity log) never contains a raw password, session token, or one-time code |
| X.4 | Append-only audit trail everywhere | Same read-only-admin pattern as `LoginEvent` (test 1.22) should apply to every future audit-style model (extraction log, activity log, twin update log) |
| X.5 | Session/link expiry is enforced server-side | Expiry checks aren't just a frontend countdown display — an expired link/session must be rejected by the backend even if the client is tampered with |
