from db import query_db

def get_project_full_details(work_id):
    """
    Fetches full project information joined across road_projects,
    ml_analysis, nlp_analysis, and risk_analysis.
    """
    sql = """
    SELECT
        p.*,
        m.anomaly_score,
        m.anomaly_detected,
        m.model_name,
        r.risk_score,
        r.risk_level,
        r.risk_reason
    FROM road_projects p
    LEFT JOIN ml_analysis m ON p.work_id = m.work_id
    LEFT JOIN risk_analysis r ON p.work_id = r.work_id
    WHERE p.work_id = %s
    """
    proj = query_db(sql, (work_id,), one=True)
    if not proj:
        return None

    # Fetch NLP similarity matches
    nlp_sql = """
    SELECT
        similarity_id,
        work_id_1,
        work_id_2,
        similarity_score,
        similarity_status,
        CASE
            WHEN work_id_1 = %s THEN work_id_2
            ELSE work_id_1
        END as matched_work_id
    FROM nlp_analysis
    WHERE work_id_1 = %s OR work_id_2 = %s
    ORDER BY similarity_score DESC
    """
    nlp_matches = query_db(nlp_sql, (work_id, work_id, work_id))

    # Also fetch the matched project description if any
    for m in nlp_matches:
        other_id = m['matched_work_id']
        other_p = query_db("SELECT description, road_type, district FROM road_projects WHERE work_id = %s", (other_id,), one=True)
        if other_p:
            m['matched_description'] = other_p['description']
            m['matched_district'] = other_p['district']

    # Parse risk reasons into a clean list
    reasons_str = proj.get('risk_reason') or ''
    reasons_list = [r.strip() for r in reasons_str.split('|') if r.strip()]

    return {
        'project': proj,
        'nlp_matches': nlp_matches,
        'reasons_list': reasons_list
    }

def get_all_alerts():
    """
    Generates dynamic alerts across the current dataset:
    - High expenditure detected
    - Project delay detected
    - Large physical-financial gap detected
    - ML anomaly detected
    - Similar project description detected
    - High-risk project detected
    """
    alerts = []

    # 1. High-risk project alerts
    high_risks = query_db("""
    SELECT p.work_id, p.state, p.district, p.description, r.risk_score, r.risk_level, r.risk_reason
    FROM road_projects p
    JOIN risk_analysis r ON p.work_id = r.work_id
    WHERE r.risk_level = 'HIGH'
    ORDER BY r.risk_score DESC
    LIMIT 20
    """)
    for r in high_risks:
        alerts.append({
            'type': 'HIGH_RISK',
            'severity': 'danger',
            'badge': 'HIGH RISK',
            'work_id': r['work_id'],
            'title': f"High-risk project detected: {r['work_id']}",
            'message': f"Risk Score: {r['risk_score']}/100. Location: {r['district']}, {r['state']}. {r['description']}",
            'reasons': [re.strip() for re in (r['risk_reason'] or '').split('|') if re.strip()]
        })

    # 2. ML Anomaly alerts
    ml_anomalies = query_db("""
    SELECT p.work_id, p.actual_expenditure, p.sanctioned_amount, p.cost_overrun_pct, m.anomaly_score
    FROM road_projects p
    JOIN ml_analysis m ON p.work_id = m.work_id
    WHERE m.anomaly_detected = 1
    ORDER BY m.anomaly_score DESC
    LIMIT 15
    """)
    for m in ml_anomalies:
        alerts.append({
            'type': 'ML_ANOMALY',
            'severity': 'danger',
            'badge': 'ML ANOMALY',
            'work_id': m['work_id'],
            'title': f"ML anomaly detected in {m['work_id']}",
            'message': f"Isolation Forest identified anomalous multidimensional patterns (Anomaly Score: {m['anomaly_score']:.2f}). Expenditure: Rs. {m['actual_expenditure']:,.0f} vs Sanctioned: Rs. {m['sanctioned_amount']:,.0f} (Overrun: {m['cost_overrun_pct']}%)",
            'reasons': ['Isolation Forest flagged expenditure/progress discrepancy']
        })

    # 3. Similar Project Description warnings
    nlp_sims = query_db("""
    SELECT work_id_1, work_id_2, similarity_score, similarity_status
    FROM nlp_analysis
    ORDER BY similarity_score DESC
    LIMIT 15
    """)
    for s in nlp_sims:
        p1 = query_db("SELECT description FROM road_projects WHERE work_id = %s", (s['work_id_1'],), one=True)
        p2 = query_db("SELECT description FROM road_projects WHERE work_id = %s", (s['work_id_2'],), one=True)
        pct = round(s['similarity_score'] * 100, 1)
        alerts.append({
            'type': 'NLP_SIMILARITY',
            'severity': 'warning',
            'badge': 'SIMILAR WORK',
            'work_id': s['work_id_1'],
            'title': f"Similar road-work description: {s['work_id_1']} ↔ {s['work_id_2']}",
            'message': f"TF-IDF Cosine Similarity: {pct}%. Work 1: '{p1['description'] if p1 else ''}' vs Work 2: '{p2['description'] if p2 else ''}'",
            'reasons': [f"High semantic similarity ({pct}%) between road works"]
        })

    # 4. Large physical-financial gap
    gaps = query_db("""
    SELECT work_id, description, physical_progress_pct, financial_progress_pct, physical_financial_gap_pct
    FROM road_projects
    WHERE physical_financial_gap_pct >= 20
    ORDER BY physical_financial_gap_pct DESC
    LIMIT 15
    """)
    for g in gaps:
        alerts.append({
            'type': 'PROGRESS_GAP',
            'severity': 'warning',
            'badge': 'PROGRESS GAP',
            'work_id': g['work_id'],
            'title': f"Large physical-financial gap: {g['work_id']}",
            'message': f"Financial drawdown: {g['financial_progress_pct']}% but Physical completion: only {g['physical_progress_pct']}% (Gap: {g['physical_financial_gap_pct']}%)",
            'reasons': ['Funds released significantly exceed ground physical construction']
        })

    # 5. Project delay alerts
    delays = query_db("""
    SELECT work_id, description, delay_days, status
    FROM road_projects
    WHERE delay_days >= 60
    ORDER BY delay_days DESC
    LIMIT 15
    """)
    for d in delays:
        alerts.append({
            'type': 'DELAY',
            'severity': 'info',
            'badge': 'DELAYED',
            'work_id': d['work_id'],
            'title': f"Project delay detected: {d['work_id']}",
            'message': f"Road project is delayed by {d['delay_days']} days beyond sanctioned completion timeline",
            'reasons': [f"Critical schedule lag ({d['delay_days']} days)"]
        })

    return alerts
