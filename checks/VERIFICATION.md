# Six-factor risk scoring verification

Executed on 30 October 2026.

- Bidder count is removed from risk scoring. Six parameter maxima sum to 100:
  anomaly 25, cost overrun 20, delay 15, progress gap 10, duplicates 20,
  expenditure versus estimate 10.
- Overrun awards are 0/6.4/12/20 and delay awards 0/4.8/9/15. Existing
  thresholds are unchanged; intermediate tiers are proportionally scaled.
- 19 unit tests passed, including threshold boundaries, exact maxima, zero and
  missing evidence, the removed bidder rule, duplicate fallback and categories.
- JavaScript interaction checks passed: six rows, correct denominators, sums,
  click-to-open explanations, fractional points and escaped evidence.
- 255 end-to-end checks passed against MariaDB: CSV and Excel imports,
  all 15,000 risk calculations, source-date delay arithmetic, all state/district
  filters, Details/reports, dashboard totals, report download and permissions.
- 11 local database checks passed. All 15,000 saved scores were refreshed and
  reconcile with the new rules. Startup refresh also updates existing scores.
- Workbook and CSV contents are unchanged: 15,000 records and 24 columns.

Validation used real database requests through Flask and a JavaScript interaction
harness. A live browser visual click-through and physical printing were not run.


## Browser account creation — 30 October 2026

- Added public Sign Up (citizen only) and administrator User Accounts/Add User.
- 41 integration assertions passed against the real MariaDB validation database:
  public registration, hashed storage, duplicate username handling, validation,
  login for all five roles, administrator role/scope assignment, permission
  restrictions, session-bound CSRF validation and a password-free account list.
- Temporary test accounts were deleted after testing. The existing users table
  is used without schema changes. Existing accounts and data are preserved.
- 19 existing unit tests passed again. All 251 existing application
  regression checks passed after the account change, including all 15,000 saved
  risk scores, pages, state/district filters, reports, permissions and syntax.
- Verification used Flask requests and real MariaDB. No live-browser visual
  review or email verification/password-reset flow is included in this update.


## Clickable contextual evidence — 30 October 2026

- Evidence scores in the contextual pair list open a six-factor explanation.
- Every one of the 20,000 saved pair scores reconciles exactly with the displayed
  point contributions. No scoring thresholds or stored analysis were changed.
- 10 integration assertions passed, including likely/possible pairs, zero-point
  factors, missing pairs, anonymous/citizen restrictions and district scope.
- JavaScript interaction harness passed: opening, requesting the selected pair,
  awarded/zero points, escaped text and error handling. Existing risk-score
  interaction checks and changed Python/JavaScript syntax checks also passed.
- Scores now display saved decimal precision. Description contribution includes
  the original total rounding, because stored cosine has only four decimals.
- Verification used Flask/MariaDB and a JavaScript harness; no live-browser
  visual inspection was performed for this update.
