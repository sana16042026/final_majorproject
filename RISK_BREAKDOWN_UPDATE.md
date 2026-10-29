> Historical checks performed before the 29 October 2026 state-balance update.
> Current dataset results are in DATASET_UPDATE_REPORT.md and DATASET_COVERAGE_TEST_RESULTS.json.
> Example risk scores can change after geography and description comparisons are rebuilt.

# Clickable risk-score breakdown

Click any combined risk score to open its calculation in project Details. The
score inside Details expands/collapses the calculation panel. Each of the seven
rows shows its recorded value/evidence, exact threshold rule, maximum points,
awarded points, and Awarded / Not awarded / Unavailable status.

For R-05637 the verified calculation is:
25 anomaly + 0 overrun + 0 delay + 0 progress gap + 5 possible overlap +
0 bidder points + 0 spending/estimate points = 30/100 (LOW).
The unavailable bidder count is explicitly marked Unavailable.

All seven rules use the same scoring function as normal processing; totals are
added and capped at 100. The previous scoring rules and stored scores remain
unchanged. A stored/current evidence mismatch is shown with a refresh notice,
rather than presenting a different total as an explanation of the saved score.
Report data and report downloads also include the breakdown. Role/district
permissions are preserved. No schema migration or data reimport is required.

## Actual checks

- 32 focused backend checks passed. Original scores, categories and reasons were
  compared against the pre-change implementation for every one of 15,000 works;
  all calculated scores also matched the stored database scores.
- Checks covered zero/financial-only/duplicate-only/both cases, threshold edges,
  the 130-to-100 cap, missing values, the actual R-05637 total, reports, permissions,
  and real SQL parameter binding for future refreshes with explanation metadata.
- 57 six-page regression checks passed against current database results.
- The actual JavaScript renderers and click handlers were executed in a Node DOM
  harness: seven rows, two awarded/four not-awarded/one unavailable states for the
  example, correct sum, collapse/expand, ARIA state, evidence escaping, and
  click-to-open Details all passed. All JavaScript syntax and Python compilation
  checks passed.
- The browser webview failed to attach on both attempts, so this particular
  change was not visually verified in a live browser. No screenshot is presented
  as evidence of the new panel. Physical printing was not exercised.

Restart the server with `python run.py`, then use Ctrl+F5. No model retraining is
needed for the displayed score explanation. Optional frontend harness:
`node validate_risk_ui.cjs` (requires Node.js).

This ZIP is a complete source copy including the master workbook. Local .env,
Python environments, Git history and runtime uploads are excluded. Existing
local database credentials were preserved in the working project.
