> Historical checks performed before the 29 October 2026 state-balance update.
> Current dataset results are in DATASET_UPDATE_REPORT.md and DATASET_COVERAGE_TEST_RESULTS.json.
> Example risk scores can change after geography and description comparisons are rebuilt.

# Outcome-estimator removal — executed checks

Date: 29 October 2026.

Removed the gradient-boosted outcome-estimation module, its model/service source
files, imports, processing calls, APIs, training controls, financial-dashboard
tab, report summary cards, and recorded-versus-estimated report/Details sections.
Fresh database initialization no longer creates its tables.

Retained: all 15,000 source works, actual date-based delay calculations, calculated
cost overrun and progress gap, Isolation Forest, description similarity, contextual
duplicate detection, risk scoring and clickable parameter breakdown, reports,
role permissions, and all six main pages. No risk weights were changed.

## Actual results

- 5 focused source/date/invalid-data tests passed.
- 41 full MySQL/Flask integration checks passed in the new isolated
  drishti_without_prediction_validation schema, including multipart master import and repeat processing.
- 32 dedicated removal checks passed against the existing app:
  removed routes return 404, no estimation controls remain, all page containers
  balance, recorded figures/risk explanations are retained, and downloads contain
  no estimated-delay or estimated-overrun fields.
- 55 six-page regression checks passed for result lists, filters,
  pagination, scope, report downloads, role permissions and JavaScript syntax.
- Clickable-risk frontend harness passed after removing the estimation section.
- All 15,000 delay values independently matched source-date arithmetic.
- New schema tables verified: duplicate_analysis, duplicate_summary, ml_analysis, nlp_analysis, risk_analysis, road_projects, users.
- Stored source / financial / risk counts: 15,000 each. Wording matches: 1,000;
  contextual pairs: 20,000. Calculations use analysis date 2026-10-29.
- Actual full-import counts: 12,720 Completed,
  1,816 Ongoing, 464 Delayed.

The full integration suite writes only its own validation schema. Current app
source records were not deleted or reimported. Any older estimator tables in an
already-existing app database are left untouched but are no longer accessed.
No live browser visual check or physical printing was repeated for this removal;
Flask-rendered HTML, inline/standalone JavaScript, APIs and report downloads were
checked. Existing synthetic-source and unsupervised-model limitations remain.

## Use the update

The existing D: project is updated. Stop its server with Ctrl+C, run
`python run.py`, then press Ctrl+F5 in the browser. No dataset reimport is required.
The ZIP contains the complete source and master workbook; local .env, Python
environments, Git metadata and runtime uploads are excluded. Configure .env from
.env.example when extracting to a new folder.
