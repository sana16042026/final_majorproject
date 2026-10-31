# Road Construction Monitoring — final-major-project

Six pages: Dashboard, Road Projects, Upload Dataset, Financial Analysis,
Similar & Duplicate Works, and Risk Analysis. Generate Report remains available
from project Details and analysis results.

## Run in VS Code

Open the folder containing run.py. Start MySQL/MariaDB in XAMPP, then:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set DB_PASS to your local database password and SECRET_KEY to your own value.
Keep an existing working .env instead of overwriting it. The default database
is drishti_final_major so older project copies keep their own saved scores.

```powershell
python import_master.py
python run.py
```

If using the virtual environment without activation, replace python with
`.\.venv\Scripts\python.exe`. Open http://127.0.0.1:5000.
Demo administrator: admin / admin123.
Stop any older project server with Ctrl+C before starting this folder.

To import the CSV instead, use `python import_master.py --format csv`.
The Upload Dataset page accepts either supplied .xlsx or .csv file. Importing
replaces the project's imported records and rebuilds all analysis results.

## Datasets

data/Master_Road_Work_Dataset_15000.xlsx and the matching .csv contain identical
15,000 records and 24 columns. Latitude and Longitude columns are removed.
The workbook's extra sheets document methodology and state coverage.

All 28 states are included: 20 have 536 works, 8 have 535. Five selected districts
are used per state, except Goa, which has all three actual districts. There are
138 state/district combinations. Union territories are outside this scope.
The data are demonstration examples, not official or independently verified
government works. Repeated dataset-type labels are omitted from display fields.
Numerical/date values and work IDs are retained from the supplied workbook.

## Risk scoring

| Parameter | Maximum | Awarded points |
| --- | ---: | --- |
| Isolation Forest anomaly | 25 | Flagged: 25; otherwise 0 |
| Cost overrun | 20 | >30%: 20; >15% to 30%: 12; >5% to 15%: 6.4; otherwise 0 |
| Recorded schedule delay | 15 | >120 days: 15; >60 to 120: 9; >20 to 60: 4.8; otherwise 0 |
| Financial minus physical progress | 10 | >25 percentage points: 10; >15 to 25: 6; >5 to 15: 2.5; otherwise 0 |
| Similar / duplicate work evidence | 20 | Strongest contextual match: likely duplicate 20; possible overlap 10; no match 0 |
| Expenditure against original estimate | 10 | Actual expenditure >=1.8 times estimated cost: 10; otherwise 0 |

Wording-only fallback contributes 20 only when contextual results are unavailable.
Contextual evidence is rounded to one decimal before selection/classification,
so the displayed evidence score and its category agree. Equal stored scores use
a stable pair order for both scoring and explanations.
The six maxima sum to exactly 100; awarded contributions are added directly.
Bidder count is not a scoring parameter. Overrun and delay tier awards are scaled
proportionally from their previous maxima; thresholds are unchanged.
LOW <40, MEDIUM 40 to <70, HIGH >=70. Missing evidence is displayed as unavailable
and contributes zero. Scores prioritize manual review and are not fraud probabilities.
Click a score to see all six parameter values, rules, awarded/max points and status.
For the illustrated negative gap plus 29-day delay and possible overlap:
0 + 0 + 4.8 + 0 + 10 + 0 = 14.8/100.

## Recorded calculations

- Completed delay = max(0, actual completion date - expected completion date).
- Unfinished delay = max(0, analysis date - expected completion date).
- Invalid or missing date prerequisites produce Unavailable.
- Overrun = max(0, (actual expenditure - sanctioned amount) / sanctioned amount * 100).
- Progress gap = financial percentage - physical percentage, in percentage points.
- Crore amounts are converted once to INR; kilometres to metres.

Isolation Forest, description similarity and contextual overlap checks remain.
The confusing gradient-boosted prediction module remains removed. Contextual
location checks use state/district/constituency/place evidence, not GPS coordinates.

## Verification

Checks and current results are grouped in checks/ to keep the main folder clear.
Node.js is needed for JavaScript validation checks, not for running the Python app.

```powershell
python -m unittest discover -s checks -p "test_*.py" -v
python checks/validate_project.py
```

Full import testing uses a separate validation database:

```powershell
python checks/validate_project.py --database drishti_final_major_validation --import-both
```

The full test uploads both formats and rebuilds their analyses in that validation
database. See checks/VERIFICATION.md for executed checks and limits.
The downloadable ZIP excludes .env, virtual environments, uploads and caches.


## Sign Up and User Accounts

- Open `/signup` from the login screen to register a citizen account. Public
  registration cannot select an official role or access scope.
- Log in as an administrator with access to all districts, then open **User
  Accounts** to add users and view the registered accounts. District-scoped
  administrators, ministries, auditors, vendors and citizens cannot add users.
- Select a role and optional scope: district name for district administrators,
  MP identifier for ministry users, required vendor identifier for contractors.
  Auditor and citizen accounts do not use a scope.
- Accounts are stored in the existing MariaDB `users` table. Passwords are hashed
  with Werkzeug; hashes and passwords are never shown in the account list.
- New passwords require 8-128 characters and confirmation. Usernames must be
  unique, 3-50 characters, using letters, numbers, dots, underscores or hyphens.
- New account forms include session-bound CSRF tokens. Existing demo logins and
  the optional `create_user.py` maintenance tool remain compatible.


## Clickable contextual evidence scores

In Similar & Duplicate Works > Contextual Duplicate Detection, click an evidence
score to see all six contributions, including zero-point factors. The explanation
uses saved match evidence; it does not rerun or alter the analysis. Same state and
district are eligibility gates, not extra points. The total is rounded to one
decimal, with its rounding included in the description contribution. This match
score is separate from the project's combined risk score.
