import os
import math
import json
import html
from io import BytesIO
from functools import wraps

from flask import (Flask, render_template, request, jsonify, send_file,
                   session, redirect, url_for)
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash

from config import Config
from db import query_db, execute_db, execute_many
from services.data_processor import process_and_save_dataset, reprocess_current_dataset
from services.report_service import get_project_full_details, get_all_alerts
from models.nlp_engine import run_nlp_similarity_analysis
from models.ml_engine import run_ml_anomaly_detection
from models.risk_engine import run_risk_analysis_for_all
from models.duplicate_engine import run_duplicate_analysis
from services.duplicate_service import (save_duplicate_results, get_duplicate_summary,
                                        get_project_duplicates)

app = Flask(__name__, template_folder='Frontend' if os.path.isdir(os.path.join(Config.BASE_DIR, 'Frontend')) else 'templates')
app.config.from_object(Config)

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DATA_FOLDER'], exist_ok=True)

# -------------------------------------------------------------
# ROLES & PERMISSIONS
# -------------------------------------------------------------
# pages  : which pages (menu items) the role can open
# ai     : may see risk scores, anomalies, NLP matches and alerts
# manage : may upload data and re-run ML / NLP
ROLES = {
    'district_admin': {
        'label': 'District Administrator',
        'pages': {'dashboard', 'projects', 'upload', 'financial-analysis', 'similar-works', 'risk-analysis', 'reports'},
        'ai': True, 'manage': True,
    },
    'ministry': {
        'label': 'Nodal Ministry / MP',
        'pages': {'dashboard', 'projects', 'financial-analysis', 'similar-works', 'risk-analysis', 'reports'},
        'ai': True, 'manage': False,
    },
    'auditor': {
        'label': 'Auditor / Investigation Agency',
        'pages': {'dashboard', 'projects', 'financial-analysis', 'similar-works', 'risk-analysis', 'reports'},
        'ai': True, 'manage': False,
    },
    'vendor': {
        'label': 'Vendor / Contractor',
        'pages': {'dashboard', 'projects'},
        'ai': False, 'manage': False,
    },
    'citizen': {
        'label': 'Citizen / Public',
        'pages': {'dashboard', 'projects'},
        'ai': False, 'manage': False,
    },
}


def current_user():
    return session.get('user')


def has_ai():
    u = current_user()
    return bool(u and ROLES[u['role']]['ai'])


def page_access(page_key):
    """Protect an HTML page: must be logged in and the role must allow the page."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for('login_page', next=request.path))
            if page_key not in ROLES[user['role']]['pages']:
                return redirect(url_for('dashboard_page'))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def api_access(permission=None):
    """Protect an API route. permission: None (any logged-in user), 'ai' or 'manage'."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return jsonify({'success': False, 'message': 'Please log in first.'}), 401
            if permission and not ROLES[user['role']][permission]:
                return jsonify({'success': False,
                                'message': 'Your role is not allowed to do this.'}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


def scope_clause(alias='p'):
    """SQL fragment + params that limit rows to what the logged-in user may see.
    District admin -> own district, Ministry/MP -> own mp_id (if set),
    Vendor -> own vendor_id. Everyone else sees all rows."""
    u = current_user()
    if not u:
        return "1=0", []
    role = u['role']
    if role == 'district_admin' and u.get('district'):
        return f"{alias}.district = %s", [u['district']]
    if role == 'ministry' and u.get('mp_id'):
        return f"{alias}.mp_id = %s", [u['mp_id']]
    if role == 'vendor':
        return f"{alias}.vendor_id = %s", [u.get('vendor_id') or '__no_vendor__']
    return "1=1", []


def project_in_scope(work_id):
    where, params = scope_clause('p')
    row = query_db(f"SELECT 1 AS ok FROM road_projects p WHERE p.work_id = %s AND {where}",
                   [work_id] + params, one=True)
    return bool(row)


_AI_KEYS = ('source_json', 'risk', 'anomaly', 'nlp', 'similar', 'ai_analysis', 'reason', 'model_name')


def sanitize_for_role(data):
    """Remove AI/risk fields (and vendor info for citizens) from nested data
    for roles that must not see them."""
    u = current_user()
    if not u or ROLES[u['role']]['ai']:
        return data
    hidden = _AI_KEYS + (('vendor',) if u['role'] == 'citizen' else ())

    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()
                    if not any(h in str(k).lower() for h in hidden)}
        if isinstance(obj, list):
            return [clean(i) for i in obj]
        return obj
    return clean(data)


@app.context_processor
def inject_user():
    """Makes current_user, role_label, allowed_pages etc. available in every template."""
    u = current_user()
    role = ROLES.get(u['role']) if u else None
    return {
        'current_user': u,
        'role_label': role['label'] if role else '',
        'allowed_pages': role['pages'] if role else set(),
        'can_manage': bool(role and role['manage']),
        'can_see_ai': bool(role and role['ai']),
    }


# -------------------------------------------------------------
# LOGIN / LOGOUT
# -------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        try:
            row = query_db("SELECT * FROM users WHERE username = %s", [username], one=True)
        except Exception:
            return render_template('login.html', error=(
                "Users table not found. Run 'python init_db.py' once, then try again."))
        if row and check_password_hash(row['password_hash'], password) and row['role'] in ROLES:
            session.clear()
            session['user'] = {
                'user_id': row['user_id'],
                'username': row['username'],
                'full_name': row['full_name'] or row['username'],
                'role': row['role'],
                'district': row['district'],
                'mp_id': row['mp_id'],
                'vendor_id': row['vendor_id'],
            }
            nxt = request.args.get('next', '')
            if nxt.startswith('/') and not nxt.startswith('//'):
                return redirect(nxt)
            return redirect(url_for('dashboard_page'))
        return render_template('login.html', error='Invalid username or password.')

    if current_user():
        return redirect(url_for('dashboard_page'))
    return render_template('login.html', error=None)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


@app.route('/api/me', methods=['GET'])
@api_access()
def api_me():
    u = current_user()
    role = ROLES[u['role']]
    return jsonify({
        'user': u,
        'role_label': role['label'],
        'pages': sorted(role['pages']),
        'can_see_ai': role['ai'],
        'can_manage': role['manage'],
    })


# -------------------------------------------------------------
# PAGE ROUTES
# -------------------------------------------------------------

@app.route('/')
@page_access('dashboard')
def dashboard_page():
    return render_template('dashboard.html', active_page='dashboard')

@app.route('/projects')
@page_access('projects')
def projects_page():
    return render_template('projects.html', active_page='projects')

@app.route('/upload')
@page_access('upload')
def upload_page():
    return render_template('upload.html', active_page='upload')

@app.route('/risk-analysis')
@page_access('risk-analysis')
def risk_page():
    return render_template('risk_analysis.html', active_page='risk-analysis', analysis_mode='risk', analysis_title='Risk Analysis', analysis_description='Combined risk scores, categories, explanations, and review alerts.')

@app.route('/financial-analysis')
@page_access('financial-analysis')
def financial_analysis_page():
    return render_template('financial_analysis.html', active_page='financial-analysis', analysis_mode='financial', analysis_title='Financial Analysis', analysis_description='Isolation Forest anomaly results with recorded spending, progress, and date-based financial indicators.')

@app.route('/similar-works')
@page_access('similar-works')
def similar_works_page():
    return render_template('similar_works.html', active_page='similar-works', analysis_mode='similarity', analysis_title='Similar & Duplicate Works', analysis_description='Compare description wording and contextual duplicate evidence. Candidates require manual verification.')

@app.route('/reports')
@page_access('reports')
def reports_page():
    return render_template('reports.html', active_page='reports')

# -------------------------------------------------------------
# REST APIS
# -------------------------------------------------------------

@app.route('/api/upload', methods=['POST'])
@api_access('manage')
def api_upload():
    """Dataset upload API (.csv or .xlsx). Validates columns and triggers data processing."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file part in the request.'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected.'}), 400

    ext = os.path.splitext(file.filename)[1].lower().replace('.', '')
    if ext not in Config.ALLOWED_EXTENSIONS:
        return jsonify({
            'success': False,
            'message': f"Invalid file type '.{ext}'. Please upload .csv or .xlsx files only."
        }), 400

    filename = secure_filename(file.filename)
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    try:
        # Run the 10-step pipeline
        result = process_and_save_dataset(save_path)
        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Data processing failed: {str(e)}"
        }), 500

@app.route('/api/load-sample', methods=['POST'])
@api_access('manage')
def api_load_sample():
    result = process_and_save_dataset(Config.MASTER_DATASET)
    return jsonify(result), 200 if result.get('success') else 400

@app.route('/api/sample/download-template', methods=['GET'])
@api_access('manage')
def download_template():
    return send_file(Config.MASTER_DATASET, as_attachment=True, download_name='Master_Road_Work_Dataset_15000.xlsx')

@app.route('/api/dashboard', methods=['GET'])
@api_access()
def api_dashboard():
    """
    Dashboard statistics, limited to the logged-in user's scope.
    Roles without AI access get no risk numbers.
    """
    where, sp = scope_clause('p')
    ai = has_ai()

    def count_projects(extra="", params=()):
        sql = f"SELECT COUNT(*) AS cnt FROM road_projects p WHERE {where} {extra}"
        return query_db(sql, list(sp) + list(params), one=True)['cnt'] or 0

    def count_risk(level):
        sql = f"""SELECT COUNT(*) AS cnt FROM risk_analysis r
                  JOIN road_projects p ON p.work_id = r.work_id
                  WHERE r.risk_level = %s AND {where}"""
        return query_db(sql, [level] + list(sp), one=True)['cnt'] or 0

    total_proj = count_projects()
    completed_proj = count_projects("AND p.status='Completed'")
    ongoing_proj = count_projects("AND p.status='Ongoing'")
    delayed_proj = count_projects("AND p.status='Delayed'")

    if ai:
        high_risk_proj = count_risk('HIGH')
        med_risk_proj = count_risk('MEDIUM')
        low_risk_proj = count_risk('LOW')
    else:
        high_risk_proj = med_risk_proj = low_risk_proj = 0

    exp_res = query_db(
        f"SELECT SUM(p.actual_expenditure) AS total_exp, SUM(p.estimated_cost) AS total_est "
        f"FROM road_projects p WHERE {where}", sp, one=True)
    total_exp = exp_res['total_exp'] or 0.0
    total_est = exp_res['total_est'] or 0.0

    status_chart = {
        'labels': ['Completed', 'Ongoing', 'Delayed'],
        'data': [completed_proj, ongoing_proj, delayed_proj]
    }
    risk_chart = {
        'labels': ['Low Risk', 'Medium Risk', 'High Risk'],
        'data': [low_risk_proj, med_risk_proj, high_risk_proj]
    }

    road_types_stats = query_db(f"""
        SELECT
            p.road_type,
            COUNT(*) AS count,
            SUM(p.estimated_cost) AS total_estimated,
            SUM(p.actual_expenditure) AS total_actual
        FROM road_projects p
        WHERE {where}
        GROUP BY p.road_type
        ORDER BY total_actual DESC
        LIMIT 6
    """, sp)

    cost_comparison_chart = {
        'labels': [r['road_type'] for r in road_types_stats],
        'estimated': [round(float(r['total_estimated'] or 0) / 100000.0, 2) for r in road_types_stats],  # Lakhs
        'actual': [round(float(r['total_actual'] or 0) / 100000.0, 2) for r in road_types_stats]         # Lakhs
    }

    recent_high_risk = []
    if ai:
        recent_high_risk = query_db(f"""
            SELECT p.work_id, p.description, p.road_type, p.state, p.district,
                   p.actual_expenditure, r.risk_score, r.risk_level, r.risk_reason
            FROM road_projects p
            JOIN risk_analysis r ON p.work_id = r.work_id
            WHERE r.risk_level = 'HIGH' AND {where}
            ORDER BY r.risk_score DESC
            LIMIT 5
        """, sp)

    analysis_dates = query_db(f'SELECT MIN(p.analysis_as_of) AS oldest, MAX(p.analysis_as_of) AS latest FROM road_projects p WHERE {where}',sp,one=True)
    u = current_user()
    return jsonify({
        'analysis_dates': analysis_dates,
        'role': u['role'],
        'role_label': ROLES[u['role']]['label'],
        'can_see_ai': ai,
        'cards': {
            'total_projects': total_proj,
            'completed_projects': completed_proj,
            'ongoing_projects': ongoing_proj,
            'delayed_projects': delayed_proj,
            'high_risk_projects': high_risk_proj,
            'total_expenditure': total_exp,
            'total_estimated': total_est
        },
        'charts': {
            'status_chart': status_chart,
            'risk_chart': risk_chart,
            'cost_comparison_chart': cost_comparison_chart
        },
        'recent_high_risk': recent_high_risk
    })

@app.route('/api/projects', methods=['GET'])
@api_access()
def api_get_projects():
    """
    Searchable and filterable projects table API (limited to the user's scope).
    Supports filters: state, district, risk_level, status, search (work_id or description)
    """
    ai = has_ai()
    state = request.args.get('state', '').strip()
    district = request.args.get('district', '').strip()
    risk_level = request.args.get('risk_level', '').strip().upper() if ai else ''
    status = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()

    scope_sql, scope_params = scope_clause('p')
    where_clauses = [scope_sql]
    params = list(scope_params)

    if state:
        where_clauses.append("p.state = %s")
        params.append(state)
    if district:
        where_clauses.append("p.district = %s")
        params.append(district)
    if risk_level:
        where_clauses.append("r.risk_level = %s")
        params.append(risk_level)
    if status:
        where_clauses.append("p.status = %s")
        params.append(status)
    if search:
        where_clauses.append("(p.work_id LIKE %s OR p.description LIKE %s)")
        like_str = f"%{search}%"
        params.extend([like_str, like_str])

    where_sql = " AND ".join(where_clauses)

    try:
        page = max(1, int(request.args.get('page', 1)))
        limit = min(500, max(10, int(request.args.get('limit', 50))))
    except (ValueError, TypeError):
        page = 1
        limit = 50

    offset = (page - 1) * limit

    count_sql = f"""
    SELECT COUNT(*) as total
    FROM road_projects p
    LEFT JOIN risk_analysis r ON p.work_id = r.work_id
    WHERE {where_sql}
    """
    total_count = query_db(count_sql, params, one=True)['total'] or 0

    sql = f"""
    SELECT
        p.work_id,
        p.description,
        p.road_type,
        p.state,
        p.district,
        p.estimated_cost,
        p.actual_expenditure,
        p.physical_progress_pct,
        p.delay_days, p.delay_basis, p.analysis_as_of, p.expected_completion_date, p.completion_date,
        p.status,
        r.risk_score,
        r.risk_level,
        m.anomaly_detected
    FROM road_projects p
    LEFT JOIN risk_analysis r ON p.work_id = r.work_id
    LEFT JOIN ml_analysis m ON p.work_id = m.work_id
    WHERE {where_sql}
    ORDER BY p.work_id ASC
    LIMIT %s OFFSET %s
    """
    page_params = list(params) + [limit, offset]
    projects = query_db(sql, page_params)

    if not ai:
        for p in projects:
            for key in ('risk_score', 'risk_level', 'anomaly_detected'):
                p.pop(key, None)

    return jsonify({
        'total': total_count,
        'page': page,
        'limit': limit,
        'total_pages': max(1, math.ceil(total_count / limit)),
        'projects': projects
    })

@app.route('/api/projects/<work_id>', methods=['GET'])
@api_access()
def api_get_project_detail(work_id):
    """Project details. AI analysis is removed for roles that may not see it."""
    if not project_in_scope(work_id):
        return jsonify({'success': False, 'message': 'Project not found'}), 404
    details = get_project_full_details(work_id)
    if not details:
        return jsonify({'success': False, 'message': 'Project not found'}), 404
    payload = sanitize_for_role(details)
    if has_ai() and isinstance(payload, dict):
        payload['location_duplicates'] = get_project_duplicates(work_id)
    return jsonify({'success': True, 'data': payload})

@app.route('/api/risk-analysis', methods=['GET'])
@api_access('ai')
def api_risk_analysis():
    """Returns risk distribution summary and high-risk projects list (scoped)."""
    where, sp = scope_clause('p')

    high_risk_list = query_db(f"""
    SELECT
        p.work_id, p.description, p.road_type, p.state, p.district,
        p.estimated_cost, p.actual_expenditure, p.cost_overrun_pct,
        p.delay_days, p.delay_basis, p.analysis_as_of, p.expected_completion_date, p.completion_date, p.physical_financial_gap_pct,
        r.risk_score, r.risk_level, r.risk_reason,
        m.anomaly_detected, m.anomaly_score
    FROM road_projects p
    JOIN risk_analysis r ON p.work_id = r.work_id
    LEFT JOIN ml_analysis m ON p.work_id = m.work_id
    WHERE r.risk_level = 'HIGH' AND {where}
    ORDER BY r.risk_score DESC
    """, sp)

    med_risk_list = query_db(f"""
    SELECT
        p.work_id, p.description, p.road_type, p.state, p.district,
        p.actual_expenditure, r.risk_score, r.risk_level, r.risk_reason
    FROM road_projects p
    JOIN risk_analysis r ON p.work_id = r.work_id
    WHERE r.risk_level = 'MEDIUM' AND {where}
    ORDER BY r.risk_score DESC
    LIMIT 20
    """, sp)

    counts = query_db(f"""
    SELECT
        SUM(CASE WHEN r.risk_level = 'HIGH' THEN 1 ELSE 0 END) as high_count,
        SUM(CASE WHEN r.risk_level = 'MEDIUM' THEN 1 ELSE 0 END) as med_count,
        SUM(CASE WHEN r.risk_level = 'LOW' THEN 1 ELSE 0 END) as low_count,
        COUNT(*) as total
    FROM risk_analysis r
    JOIN road_projects p ON p.work_id = r.work_id
    WHERE {where}
    """, sp, one=True)

    return jsonify({
        'counts': counts,
        'high_risk_projects': high_risk_list,
        'medium_risk_sample': med_risk_list
    })

@app.route('/api/risk-analysis/projects', methods=['GET'])
@api_access('ai')
def api_risk_projects():
    """Paginated list of projects for one risk level (HIGH / MEDIUM / LOW), limited to the user's scope."""
    level = request.args.get('level', 'MEDIUM').strip().upper()
    if level not in ('HIGH', 'MEDIUM', 'LOW'):
        return jsonify({'success': False, 'message': 'level must be HIGH, MEDIUM or LOW.'}), 400

    search = request.args.get('search', '').strip()
    try:
        page = max(1, int(request.args.get('page', 1)))
        limit = min(200, max(10, int(request.args.get('limit', 25))))
    except (ValueError, TypeError):
        page, limit = 1, 25

    scope_sql, scope_params = scope_clause('p')
    clauses = [scope_sql, "r.risk_level = %s"]
    params = list(scope_params) + [level]
    if search:
        clauses.append("(p.work_id LIKE %s OR p.description LIKE %s)")
        like = f"%{search}%"
        params.extend([like, like])
    where_sql = " AND ".join(clauses)

    total = query_db(f"""
        SELECT COUNT(*) AS total
        FROM road_projects p
        JOIN risk_analysis r ON p.work_id = r.work_id
        WHERE {where_sql}
    """, params, one=True)['total'] or 0

    rows = query_db(f"""
        SELECT p.work_id, p.description, p.road_type, p.state, p.district,
               p.actual_expenditure, p.cost_overrun_pct, p.delay_days,
               p.physical_financial_gap_pct,
               r.risk_score, r.risk_level, r.risk_reason
        FROM road_projects p
        JOIN risk_analysis r ON p.work_id = r.work_id
        WHERE {where_sql}
        ORDER BY r.risk_score DESC, p.work_id ASC
        LIMIT %s OFFSET %s
    """, params + [limit, (page - 1) * limit])

    return jsonify({
        'level': level,
        'total': total,
        'page': page,
        'limit': limit,
        'total_pages': max(1, math.ceil(total / limit)),
        'projects': rows
    })

@app.route('/api/duplicates/summary', methods=['GET'])
@api_access('ai')
def api_duplicate_summary():
    """Counts from the location-aware duplicate check (scoped), plus how many
    description-only matches were in a different district and therefore not flagged."""
    scope_a, params_a = scope_clause('a')
    scope_b, params_b = scope_clause('b')
    counts, wording = None, None
    try:
        counts = query_db(f"""
            SELECT COUNT(*) AS pairs,
                   CAST(COALESCE(SUM(CASE WHEN d.classification = 'Likely duplicate' THEN 1 ELSE 0 END), 0) AS SIGNED) AS likely,
                   CAST(COALESCE(SUM(CASE WHEN d.classification = 'Possible overlap' THEN 1 ELSE 0 END), 0) AS SIGNED) AS possible
            FROM duplicate_analysis d
            JOIN road_projects a ON a.work_id = d.work_id_1
            JOIN road_projects b ON b.work_id = d.work_id_2
            WHERE {scope_a} AND {scope_b}
        """, params_a + params_b, one=True)
    except Exception:
        pass
    try:
        wording = query_db(f"""
            SELECT COUNT(*) AS description_pairs,
                   CAST(COALESCE(SUM(CASE WHEN a.state <> b.state OR a.district <> b.district
                                          THEN 1 ELSE 0 END), 0) AS SIGNED) AS different_location
            FROM nlp_analysis n
            JOIN road_projects a ON a.work_id = n.work_id_1
            JOIN road_projects b ON b.work_id = n.work_id_2
            WHERE {scope_a}
        """, params_a, one=True)
    except Exception:
        pass
    return jsonify({'summary': get_duplicate_summary(), 'counts': counts, 'description_only': wording})

@app.route('/api/duplicates/projects', methods=['GET'])
@api_access('ai')
def api_duplicate_projects():
    """Paginated duplicate / overlap pairs. kind = all | likely | possible (scoped)."""
    kind = request.args.get('kind', 'all').strip().lower()
    if kind not in ('all', 'likely', 'possible'):
        return jsonify({'success': False, 'message': 'kind must be all, likely or possible.'}), 400
    search = request.args.get('search', '').strip()
    try:
        page = max(1, int(request.args.get('page', 1)))
        limit = min(200, max(10, int(request.args.get('limit', 25))))
    except (ValueError, TypeError):
        page, limit = 1, 25

    scope_a, params_a = scope_clause('a')
    scope_b, params_b = scope_clause('b')
    clauses = [scope_a, scope_b]
    params = params_a + params_b
    if kind == 'likely':
        clauses.append("d.classification = 'Likely duplicate'")
    elif kind == 'possible':
        clauses.append("d.classification = 'Possible overlap'")
    if search:
        clauses.append("(d.work_id_1 LIKE %s OR d.work_id_2 LIKE %s OR a.description LIKE %s OR b.description LIKE %s)")
        like = f"%{search}%"
        params = params + [like, like, like, like]
    where_sql = " AND ".join(clauses)

    try:
        total = query_db(f"""
            SELECT COUNT(*) AS total
            FROM duplicate_analysis d
            JOIN road_projects a ON a.work_id = d.work_id_1
            JOIN road_projects b ON b.work_id = d.work_id_2
            WHERE {where_sql}
        """, params, one=True)['total'] or 0
        rows = query_db(f"""
            SELECT d.work_id_1, a.description AS description_1,
                   d.work_id_2, b.description AS description_2,
                   a.district, a.state,
                   d.text_similarity, d.evidence_score, d.classification, d.evidence
            FROM duplicate_analysis d
            JOIN road_projects a ON a.work_id = d.work_id_1
            JOIN road_projects b ON b.work_id = d.work_id_2
            WHERE {where_sql}
            ORDER BY d.evidence_score DESC, d.pair_id ASC
            LIMIT %s OFFSET %s
        """, params + [limit, (page - 1) * limit])
    except Exception:
        return jsonify({'success': False,
                        'message': "Duplicate tables not found. Run 'python init_db.py' and upload a dataset."}), 500

    return jsonify({
        'kind': kind, 'total': total, 'page': page, 'limit': limit,
        'total_pages': max(1, math.ceil(total / limit)),
        'pairs': rows
    })

@app.route('/api/run-duplicates', methods=['POST'])
@api_access('manage')
def api_run_duplicates():
    result = reprocess_current_dataset()
    return jsonify(result), 200 if result.get('success') else 400

@app.route('/api/alerts', methods=['GET'])
@api_access()
def api_alerts():
    """Dynamic alerts. Roles without AI access get an empty list."""
    if not has_ai():
        return jsonify({'total_alerts': 0, 'alerts': []})

    alerts = get_all_alerts()

    where, sp = scope_clause('p')
    if where != "1=1":
        allowed = {r['work_id'] for r in query_db(
            f"SELECT p.work_id FROM road_projects p WHERE {where}", sp)}
        alerts = [a for a in alerts
                  if not isinstance(a, dict)
                  or a.get('work_id') is None
                  or a.get('work_id') in allowed]

    return jsonify({
        'total_alerts': len(alerts),
        'alerts': alerts
    })

@app.route('/api/filters', methods=['GET'])
@api_access()
def api_filters():
    """Distinct states, districts, road types, statuses (only values inside the user's scope)."""
    where, sp = scope_clause('p')
    selected_state = request.args.get('state', '').strip()

    def distinct(col, state=None):
        sql = f"SELECT DISTINCT p.{col} AS v FROM road_projects p WHERE {where}"
        params = list(sp)
        if state:
            sql += " AND p.state = %s"
            params.append(state)
        sql += f" AND p.{col} IS NOT NULL AND p.{col} <> '' ORDER BY p.{col}"
        return [r['v'] for r in query_db(sql, params)]

    return jsonify({
        'states': distinct('state'),
        # Only districts inside the chosen state (all districts when no state is chosen)
        'districts': distinct('district', selected_state),
        'road_types': distinct('road_type'),
        'statuses': distinct('status')
    })

@app.route('/api/run-nlp', methods=['POST'])
@api_access('manage')
def api_run_nlp():
    result = reprocess_current_dataset()
    return jsonify(result), 200 if result.get('success') else 400

@app.route('/api/run-ml', methods=['POST'])
@api_access('manage')
def api_run_ml():
    result = reprocess_current_dataset()
    return jsonify(result), 200 if result.get('success') else 400

@app.route('/api/reports/project/<work_id>', methods=['GET'])
@api_access('ai')
def api_project_report(work_id):
    """Complete project report data (admin, ministry, auditor only)."""
    if not project_in_scope(work_id):
        return jsonify({'success': False, 'message': 'Project not found.'}), 404
    details = get_project_full_details(work_id)
    if not details:
        return jsonify({'success': False, 'message': 'Project not found.'}), 404
    if isinstance(details, dict):
        details['location_duplicates'] = get_project_duplicates(work_id)
    return jsonify({'success': True, 'report': details})

@app.route('/api/reports/summary', methods=['GET'])
@api_access('ai')
def api_summary_report():
    """System-wide summary report data, limited to the user's scope."""
    where, sp = scope_clause('p')

    def one(sql, params=()):
        return query_db(sql, list(params), one=True)

    total_projects = one(f"SELECT COUNT(*) AS c FROM road_projects p WHERE {where}", sp)['c'] or 0
    sums = one(f"""SELECT SUM(p.actual_expenditure) AS exp, SUM(p.sanctioned_amount) AS sanc
                   FROM road_projects p WHERE {where}""", sp)
    total_exp = sums['exp'] or 0
    total_sanctioned = sums['sanc'] or 0
    high_risk_count = one(f"""SELECT COUNT(*) AS c FROM risk_analysis r
                              JOIN road_projects p ON p.work_id = r.work_id
                              WHERE r.risk_level='HIGH' AND {where}""", sp)['c'] or 0
    anomalies_count = one(f"""SELECT COUNT(*) AS c FROM ml_analysis m
                              JOIN road_projects p ON p.work_id = m.work_id
                              WHERE m.anomaly_detected=1 AND {where}""", sp)['c'] or 0
    nlp_count = one(f"""SELECT COUNT(*) AS c FROM nlp_analysis n
                        JOIN road_projects p ON p.work_id = n.work_id_1
                        WHERE {where}""", sp)['c'] or 0

    high_risk_projects = query_db(f"""
    SELECT p.work_id, p.description, p.road_type, p.state, p.district,
           p.actual_expenditure, r.risk_score, r.risk_level, r.risk_reason
    FROM road_projects p
    JOIN risk_analysis r ON p.work_id = r.work_id
    WHERE r.risk_level = 'HIGH' AND {where}
    ORDER BY r.risk_score DESC
    LIMIT 25
    """, sp)

    # Location-aware duplicate summary.
    scope_a, params_a = scope_clause('a')
    scope_b, params_b = scope_clause('b')
    likely_duplicates = possible_overlaps = 0
    try:
        dup = one(f"""
            SELECT CAST(COALESCE(SUM(CASE WHEN d.classification = 'Likely duplicate' THEN 1 ELSE 0 END), 0) AS SIGNED) AS likely,
                   CAST(COALESCE(SUM(CASE WHEN d.classification = 'Possible overlap' THEN 1 ELSE 0 END), 0) AS SIGNED) AS possible
            FROM duplicate_analysis d
            JOIN road_projects a ON a.work_id = d.work_id_1
            JOIN road_projects b ON b.work_id = d.work_id_2
            WHERE {scope_a} AND {scope_b}""", params_a + params_b)
        likely_duplicates, possible_overlaps = dup['likely'] or 0, dup['possible'] or 0
    except Exception:
        pass
    return jsonify({
        'summary': {
            'total_projects': total_projects,
            'total_expenditure': total_exp,
            'total_sanctioned': total_sanctioned,
            'high_risk_count': high_risk_count,
            'anomalies_count': anomalies_count,
            'nlp_similarity_count': nlp_count,
            'likely_duplicates': likely_duplicates,
            'possible_overlaps': possible_overlaps
        },
        'high_risk_projects': high_risk_projects
    })

@app.route('/api/reports/project/<work_id>/download', methods=['GET'])
@api_access('ai')
def download_project_report(work_id):
    if not project_in_scope(work_id):
        return jsonify({'success': False, 'message': 'Project not found.'}), 404
    report = get_project_full_details(work_id)
    if not report:
        return jsonify({'success': False, 'message': 'Project not found.'}), 404
    report['location_duplicates'] = get_project_duplicates(work_id)
    p = report['project']
    content = '<!doctype html><html><head><meta charset="utf-8"><title>DRISHTI Work Report</title><style>body{font:16px system-ui;margin:40px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style></head><body>'
    content += '<h1>DRISHTI Work Report: '+html.escape(work_id)+'</h1>'
    content += '<h2>Calculated delay: '+html.escape(str(p['delay_days']) if p['delay_days'] is not None else 'Unavailable')+' days</h2>'
    content += '<p>'+html.escape(p.get('delay_basis') or 'Unavailable')+'; as of '+html.escape(str(p.get('analysis_as_of')))+'</p>'
    content += '<p>Financial amounts are INR. Model estimates and review scores require human verification.</p>'
    content += '<pre>'+html.escape(json.dumps(report,indent=2,default=str))+'</pre></body></html>'
    return send_file(BytesIO(content.encode('utf-8')),mimetype='text/html',as_attachment=True,
                     download_name='DRISHTI_'+secure_filename(work_id)+'_Report.html')



def analysis_pagination():
    try:
        return max(1,int(request.args.get('page',1))),min(100,max(10,int(request.args.get('limit',25))))
    except (ValueError,TypeError):
        return 1,25

@app.route('/api/financial-analysis/projects')
@api_access('ai')
def financial_analysis_projects():
    page,limit=analysis_pagination()
    scope,params=scope_clause('p')
    filters=[scope]
    search=request.args.get('search','').strip()
    kind=request.args.get('kind','anomalies')
    if kind not in {'anomalies','normal','all'}:
        return jsonify(success=False,message='Invalid financial result filter.'),400
    if kind!='all':
        filters.append('m.anomaly_detected=%s');params.append(1 if kind=='anomalies' else 0)
    if search:
        filters.append('(p.work_id LIKE %s OR p.description LIKE %s)');params+=['%'+search+'%']*2
    clause=' AND '.join(filters)
    total=query_db(f'SELECT COUNT(*) AS n FROM ml_analysis m JOIN road_projects p ON p.work_id=m.work_id WHERE {clause}',params,one=True)['n']
    rows=query_db(f"""SELECT p.work_id,p.description,p.state,p.district,p.actual_expenditure,m.anomaly_score,m.anomaly_detected
        FROM ml_analysis m JOIN road_projects p ON p.work_id=m.work_id WHERE {clause}
        ORDER BY m.anomaly_score DESC,p.work_id LIMIT %s OFFSET %s""",params+[limit,(page-1)*limit])
    scope,sp=scope_clause('p')
    stats=query_db(f"""SELECT COUNT(*) AS analysed, COALESCE(SUM(m.anomaly_detected=1),0) AS flagged,
        COALESCE(SUM(m.anomaly_detected=0),0) AS normal
        FROM ml_analysis m JOIN road_projects p ON p.work_id=m.work_id WHERE {scope}""",sp,one=True)
    return jsonify(total=total,page=page,limit=limit,total_pages=max(1,math.ceil(total/limit)),projects=rows,summary=stats)

@app.route('/api/similarity/projects')
@api_access('ai')
def description_similarity_projects():
    page,limit=analysis_pagination()
    sa,pa=scope_clause('a');sb,pb=scope_clause('b')
    filters=[sa,sb];params=pa+pb
    search=request.args.get('search','').strip()
    if search:
        filters.append('(a.work_id LIKE %s OR b.work_id LIKE %s OR a.description LIKE %s OR b.description LIKE %s)')
        params+=['%'+search+'%']*4
    clause=' AND '.join(filters)
    joins='FROM nlp_analysis n JOIN road_projects a ON a.work_id=n.work_id_1 JOIN road_projects b ON b.work_id=n.work_id_2'
    total=query_db(f'SELECT COUNT(*) AS n {joins} WHERE {clause}',params,one=True)['n']
    rows=query_db(f"""SELECT n.work_id_1,n.work_id_2,n.similarity_score,n.similarity_status,
        a.description AS description_1,b.description AS description_2,a.state AS state_1,a.district AS district_1,
        b.state AS state_2,b.district AS district_2 {joins} WHERE {clause}
        ORDER BY n.similarity_score DESC,n.similarity_id LIMIT %s OFFSET %s""",params+[limit,(page-1)*limit])
    return jsonify(total=total,page=page,limit=limit,total_pages=max(1,math.ceil(total/limit)),pairs=rows)

if __name__ == '__main__':
    app.run(host=Config.APP_HOST, port=Config.APP_PORT, debug=True)
