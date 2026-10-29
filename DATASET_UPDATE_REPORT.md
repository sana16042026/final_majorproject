# Balanced synthetic dataset update

Updated and tested on 29 October 2026.

## Dataset

- Exactly 15,000 unique work IDs, all clearly labelled synthetic in Progress_Basis.
- All 28 Indian states. Twenty have 536 records and eight have 535 records.
- 138 state/district combinations: five selected districts per state, except Goa,
  which has all three actual districts (North Goa, South Goa, Kushavati).
- District allocations within each state differ by at most one record.
- Existing numerical/date examples, IDs, vendors and work/road types retained.
  Descriptions, titles, state/district assignments, fictional site and administrative
  labels regenerated consistently with seed 20261029. Coordinates are unavailable.
- The workbook keeps its original 26 import columns and Data_Dictionary sheet.
  Dataset guide and State coverage sheets explain the synthetic geography.
- Equal state allocation is for demonstrations, not real-world representativeness.
  These are not verified government road works or fraud labels.

## Application

The configured local application's database was backed up and then reimported
from the updated master. Isolation Forest, description similarity, contextual
duplicates, risk scores and reports were rebuilt. All six pages are retained.
Delay/overrun/gap formulas and risk weights are unchanged. The confusing
gradient-boosted prediction module remains removed.

## Executed verification

- 5 focused mapping/date/invalid-data tests passed.
- 41 complete MySQL/Flask integration checks passed in an isolated
  drishti_balanced_states_validation schema, including full upload, actual date calculations,
  rollback, repeated processing, reports and access permissions.
- 291 read-only checks passed against the updated application:
  workbook/database consistency, all 28 state filters, every one of the 138
  state/district filters, state-level project reports and risk-point reconciliation.
- 55 six-page regression checks and 32 prediction-removal
  checks passed. Clickable-risk frontend harness and JavaScript syntax passed.
- All 15,000 date-based delays independently matched source-date arithmetic.
- Current integration table counts: {"road_projects": 15000, "ml_analysis": 15000, "risk_analysis": 15000, "nlp_analysis": 1000, "duplicate_analysis": 20000}.
- Current status counts at 2026-10-29: {"Completed": 12720, "Ongoing": 1816, "Delayed": 464}.

Workbook previews were visually checked. App checks use Flask-rendered pages,
APIs and a JavaScript interaction harness; a live browser click-through and
physical printing were not performed for this update.

## Run

For the existing updated D: folder: restart with `python run.py` and refresh the
browser with Ctrl+F5. The current local database already contains the new data.
For a new extraction or a different existing database: configure .env from
.env.example, start MySQL/MariaDB, install requirements, then run
`python import_master.py` once before `python run.py`. Import replaces that
database's current road-project snapshot and rebuilds all analysis results.

The ZIP excludes credentials, Python environments, database backups, uploads
and Git metadata. The pre-update workbook/database backup is outside the project
at D:\Projects\DRISHTI_Backup_Before_State_Balance_20261029.
