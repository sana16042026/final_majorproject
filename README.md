# DRISHTI AI — Road-work Monitoring

The project uses a clearly labelled, balanced synthetic 15,000-record master workbook and retains six pages:
Dashboard, Road Projects, Upload Dataset, Financial Analysis, Similar & Duplicate
Works, and Risk Analysis. Reports are available through Generate Report actions.

## Analysis components

1. Isolation Forest financial anomaly detection.
2. TF-IDF/cosine description similarity.
3. Location-aware contextual duplicate detection.
4. Deterministic risk scoring, with clickable parameter-by-parameter explanations.

The gradient-boosted delay/cost-overrun estimator has been removed. Actual delay,
cost overrun and progress gap remain calculated from source records, not estimated.

## Run on Windows

Start MySQL/MariaDB in XAMPP. In this project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set your local DB_PASS and SECRET_KEY in .env. For a fresh database:

```powershell
.\.venv\Scripts\python.exe import_master.py
```

For an existing database, run `python import_master.py` once to replace its old
10-state dataset and rebuild all analyses using the balanced workbook. This replaces
the current imported project records. Keep a database backup if they include your own uploads.
Start the website:

```powershell
.\.venv\Scripts\python.exe run.py
```

Open http://127.0.0.1:5000. Demo administrator: admin / admin123. Existing local
.env credentials are preserved when updating the working project. The ZIP excludes
.env, virtual environments, Git metadata and runtime uploads.

## Recorded calculations

- Completed delay: max(0, actual completion date − expected completion date).
- Unfinished delay: max(0, analysis date − expected completion date).
- Missing or inconsistent dates: Unavailable.
- Overrun: max(0, (expenditure − sanction) / sanction × 100).
- Progress gap: source financial percentage − source physical percentage.
- Crore source amounts are converted once to INR; kilometres to metres.
- Original source fields are preserved in source_json. Physical and financial
  progress values are imported from the workbook. Financial progress above 100%
  remains valid overrun evidence. Missing contract/bidder figures are unavailable.

The three analysis dashboards group four underlying components. There is no
recorded-versus-predicted panel, estimation tab, training control, prediction API,
or prediction dependency in imports/reprocessing/reports. Fresh initialization
does not create estimator tables. Previously existing legacy estimator tables are
left untouched but are no longer read or written; source data is preserved.

## Review results

Isolation Forest uses the existing custom NumPy implementation and 15% review
fraction. Description similarity keeps its strongest 1,000 pairs; contextual
duplicates keep their existing evidence rules and 20,000-pair cap. Risk uses the
existing rule points, capped at 100: LOW <40, MEDIUM 40–<70, HIGH ≥70. Clicking a
score shows all seven parameters, including zero-point and unavailable evidence.
These are human-review signals, not fraud probabilities or proof of wrongdoing.
The supplied Progress_Basis field includes synthetic entries, so the workbook is
not presented as independently verified government data.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest test_master_dataset -v
.\.venv\Scripts\python.exe -u test_e2e.py
.\.venv\Scripts\python.exe validate_six_pages.py
```

The end-to-end suite uses its own drishti_balanced_states_validation schema,
not the application database. It imports and reprocesses all 15,000 records and
checks actual calculations, rollback, reports and access. The page validator is
read-only against the configured application database and requires Node.js for
syntax checks. See DATASET_UPDATE_REPORT.md for the executed checks and limitations.

## Balanced synthetic dataset (29 October 2026)

All 28 Indian states are included: 20 have 536 records and 8 have 535 records.
There are 138 state/district combinations. Five selected districts are used for
each state except Goa, where all three actual districts are included: North Goa,
South Goa and Kushavati. Union territories are outside the requested 28-state scope.
Within each state, district record counts differ by at most one.

All records are synthetic demonstration data. The supplied workbook's numerical
and date examples are preserved. State/district assignments, descriptions, sites,
constituencies, implementing agencies and representative labels were regenerated
consistently with fixed seed 20261029. They are not actual observations for these
districts. GPS coordinates are blank because no verified road coordinates exist.
Every source record is marked SYNTHETIC in Progress_Basis. State coverage and
methodology are documented in the workbook and data/DATASET_COVERAGE.json.

State balance helps demonstrate filtering across India; it does not establish
real-world representativeness or fraud-detection accuracy. The district names
were checked against government directories, including https://igod.gov.in/sg/district/states
and https://www.goa.gov.in/know-goa/districts-of-goa/.

The original 26-column import format and work IDs remain compatible. All saved
ML, wording, contextual-duplicate and risk results must be rebuilt after import,
because new geography and descriptions change the comparison groups. Actual
delay, overrun and gap formulas are unchanged. The removed prediction module
remains removed. Run `python validate_dataset_coverage.py` to check the workbook,
database, all state/district filters and reports against this coverage manifest.
