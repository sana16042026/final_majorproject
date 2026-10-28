# DRISHTI AI — Master Road Workbook Update

This is the existing `major-project (3).zip` app, updated for the supplied
`data/Master_Road_Work_Dataset_15000.xlsx`. It retains its existing dashboard,
financial anomaly detection, description similarity, contextual duplicate checks,
risk rules, delay/cost outcome estimates, roles, and reports. Earlier chat prompts
were not used as additional requirements.

## Run on Windows

Start MySQL from your XAMPP control panel. Open PowerShell in this extracted folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe import_master.py
.\.venv\Scripts\python.exe run.py
```

Open http://127.0.0.1:5000 and log in as `admin` / `admin123`.
Other existing demo accounts are created by init_db.py. Your real MySQL credentials
can be set in `.env`; defaults are local root with an empty password. The updated
app uses a separate database named `drishti_master_road`, so it does not replace
your old application database. Importing replaces records within this database.
Use your configured password if local root does not have an empty password.

The supplied `.env` points the optional auto-start binary to D:\xampp. However,
copying XAMPP alone does not migrate MySQL: its my.ini may still point to C:.
This update does not change your MySQL installation or move database files.
Start a working MySQL server normally; the app connects to localhost:3306.

Startup automatically imports the bundled master only if the app database is
empty. On later dates, startup refreshes delay and dependent analysis. While the
app stays running, use **Refresh delays & all analysis** to advance the reporting
date. No new synthetic sample dataset is generated.

## Dataset mapping

The single supplied workbook has 15,000 records and 26 fields. `Work_Description`
maps to description; `Vendor_Name` to vendor_id; `Elected_MP` to mp_id;
`Progress_Percentage` to physical progress; `Financial_Percentage` to financial
progress. Financial progress above 100% is retained as legitimate overrun evidence;
physical progress must remain between 0 and 100%. Road_Length_KM is converted to length_m. Four financial columns ending
in INR_Crore are multiplied by 10,000,000 once, preserving the existing app's
INR storage and currency-formatting contract. Legacy normalized columns are
already INR and are not multiplied again during reprocessing.

All original columns and original units are preserved in source_json, including
Invested_Amount_INR, Progress_Basis, coordinates, payment status, and source dates.
Original values can be inspected in API/HTML reports. The original workbook is
also downloadable from Upload. Old bundled uploads, sample generator, archived
templates and machine-specific virtual environments are excluded from the package.

Unavailable tender/agreement/final amounts or bidder counts stay NULL; they are
not fabricated from other figures. Financial model features use the available
source and documented derived metrics. No ground-truth fraud labels are created.

## Delayed days

Calculations use Asia/Kolkata calendar dates, with `analysis_as_of` stored per work:

- Completed with valid actual and expected dates: max(0, completion − expected).
- Unfinished with a valid expected date: max(0, reporting date − expected).
- Completed with 100% progress but no actual completion date: Unavailable.
- Missing or inconsistent dates (e.g. expected before start): Unavailable.

`Not Completed`, dashes and invalid date text are treated as missing dates.
Completed work stays Completed even if it finished late; its delay is still shown.
Unfinished work with any positive overdue days is Delayed, otherwise Ongoing.
Completely absent status evidence gives Unavailable. Original date fields,
delay_basis and analysis_as_of are persisted and shown in Details and reports.
R-00001 in this workbook is 29 days late (2023-04-27 versus 2023-03-29).

## Processing and models

Uploads map/clean source values, calculate delay/status/cost overrun/progress gap,
run the existing modules, and atomically replace source records and ALL derived
tables. An insertion failure rolls back the entire refresh. Rerun buttons refresh
the complete pipeline, preventing stale risk/prediction results after dates change.

Description similarity is computed in small blocks rather than a full 15,000²
dense matrix; the existing strongest-1000 output cap is retained. Contextual
duplicates retain the existing same-location/evidence rules and 20,000-pair cap.
Candidate lists are bounded, not exhaustive proof of duplicate expenditure.

Existing custom Isolation Forest and risk thresholds remain in place. The
outcome flags use the documented fixed thresholds (>30 days, >15% overrun),
replacing a prevalence cutoff that could flag zero-overrun estimates.
The
prediction module estimates observed date-derived delay and observed cost overrun
using its existing five-fold validation. Unfinished-work overdue days are current
observations, NOT final completion labels or a guarantee of future delay.
Rows with unavailable targets are excluded from prediction fitting. The source
Progress_Basis itself describes synthetic values for some records, so metrics
measure this provided dataset and do not establish real-world fraud accuracy.

## Reports

Details, project lists, dashboard, risk tables and reports use the current database.
The Reports page supports browser Print/PDF plus **Download report**, which returns
a standalone HTML report including original source values, calculated delay,
analysis date, financial/risk evidence, duplicate matches and model estimates.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest test_master_dataset -v
.\.venv\Scripts\python.exe -u test_e2e.py
```

Fast tests cover mapping, missing/invalid values, all delay cases, and daily
unfinished-delay increments. The real MySQL suite uses its own dedicated schema
`drishti_master_validation_v3`, uploads all 15,000 rows through Flask, independently
checks every date calculation and currency units, tests routes/filters/reports,
simulates failure to verify rollback, and reprocesses to check repeatability.
`TEST_RESULTS.json` records an actual successful full run. See TEST_REPORT.md for
executed checks, browser verification and limitations.

## Configuration after cloning

The repository excludes local passwords, Python environments, caches, and runtime
uploads. Copy the example configuration before following the setup steps above:

```powershell
Copy-Item .env.example .env
```

Set DB_PASS to your local MariaDB/MySQL password. The supplied master workbook
remains in data/. HTML pages are in Frontend/; the application also accepts the
original templates/ folder name.
