# Executed validation results

Validation date: 28 October 2026 (Asia/Kolkata).

- 44 real-MySQL/Flask integration checks passed in the isolated
  `drishti_master_validation_v3` database. The original application database was not changed.
- Six focused unit tests passed: master mapping, date cases, invalid numeric data,
  next-day refresh behavior, >100% financial progress, and zero-overrun flag rules.
- All Python files compile; all 15 application modules import successfully.
  Every standalone JavaScript file passed `node --check`.
- Master workbook SHA-256 matches the user-supplied D: file exactly:
  `892cc6dcda5e5e8cd8d48e26c7cc19c57c1bed34cefebfe7112d11d394988e5d`.

## Actual database results

- Source works: 15,000.
- Financial analysis: 15,000.
- Risk analysis: 15,000.
- Outcome estimates: 15,000.
- Description similarity pairs: 1,000.
- Contextual duplicate candidates: 20,000.
- Completed: 12,720; ongoing: 1,826;
  currently overdue/Delayed: 454.
- Calculated delay range: 0–237 days.
- Every one of the 15,000 date-derived delay values was independently verified
  against the source dates, using reporting date 2026-10-28.
- A deliberately failed storage transaction preserved the previous complete
  published dataset. Reprocessing refreshed all analysis tables without duplicates.

## Browser checks

The app ran locally against the validation database. The browser successfully
logged in as administrator, displayed the populated dashboard (15,000 total;
12,720 completed; 1,826 ongoing; 454 overdue), searched the project list for
R-00001, and opened its Details. The visible Details confirmed 29 days delay,
expected completion 29 March 2023, actual completion 27 April 2023, and the
28 October 2026 reporting date. The browser's Delayed filter returned 454 works;
its first displayed work had 25 overdue days and Delayed status. The Reports page populated its summary and
rendered a project report. HTTP tests verified downloadable reports and the
unchanged master workbook download. BROWSER_DELAY_CHECK.jpg records the
browser's Details modal showing the 29-day delay and both source dates.

## Limits and environment details

- Browser automation intermittently timed out. Login, populated dashboard,
  project search/details, and a populated report were observed successfully;
  exhaustive browser interaction with every risk tab was not performed.
- Physical printing and the operating-system Save-as-PDF dialog were not exercised.
  HTML report downloads were tested through the real Flask route and MySQL data.
- The existing fixed sidebar/table layout can scroll horizontally in a narrow
  browser panel. This task updates data and calculations without rebuilding it.
- The running server reports its data directory as C:\xampp\mysql\data even
  though XAMPP has been copied to D:. This update does not migrate that server.
- Model outputs are estimates/review signals from the supplied data, which includes
  synthetic source progress descriptions. No real-world fraud accuracy is claimed.
- Description matching retains its 1,000-pair cap; contextual duplicates retain
  their 20,000-pair cap, so neither candidate list is exhaustive.
- Delays for unfinished works are observed as of the last refresh. Restart the
  app on a later date or use Refresh delays & all analysis to update them.

See TEST_RESULTS.json for the exact integration check list and README.md for setup.
