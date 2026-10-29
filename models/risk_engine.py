def calculate_project_risk(project, ml_result=None, nlp_matches=None, duplicate_matches=None):
    """
    Explainable AI Risk Scoring Engine (0 to 100).
    Combines:
    1. ML Isolation Forest Anomaly Detection
    2. Cost Overrun %
    3. Project Delay (days)
    4. Physical vs Financial Progress Gap
    5. Location-aware Duplicate / Overlap Check (same district, backed by place,
       road type, length and cost). When the location-aware check did not run
       (duplicate_matches is None) the older description-only NLP match is used.
    6. Expenditure & Bidding Pattern
    """
    score = 0.0
    reasons = []
    components = []
    def component(key, label, value, rule, maximum, available=True):
        points = round(score - sum(row['points'] for row in components), 6)
        components.append(dict(key=key, parameter=label, value=value if available else None,
            rule=rule, points=points, maximum_points=maximum,
            status='Awarded' if points else 'Not awarded' if available else 'Unavailable',
            explanation='Condition met; points added.' if points else
                'Condition not met; no points added.' if available else
                'Source value or detection evidence is unavailable; no points added.'))


    # 1. ML Anomaly Result (+25 points)
    is_ml_anomaly = False
    if ml_result and ml_result.get('anomaly_detected') == 1:
        is_ml_anomaly = True
        score += 25.0
        reasons.append("ML Anomaly Detected (Isolation Forest flagged unusual multidimensional pattern)")

    component('financial_anomaly', 'Isolation Forest anomaly',
        ('Flagged' if is_ml_anomaly else 'Not flagged') + (f"; model score {ml_result.get('anomaly_score')}" if ml_result else ''),
        'Flagged by Isolation Forest: +25; otherwise +0.', 25, ml_result is not None)

    # 2. Cost Overrun (up to +25 points)
    cost_overrun = float(project.get('cost_overrun_pct', 0.0) or 0.0)
    actual_exp = float(project.get('actual_expenditure', 0.0) or 0.0)
    sanctioned = float(project.get('sanctioned_amount', 0.0) or 0.0)

    # Recalculate cost overrun if needed
    if cost_overrun <= 0 and sanctioned > 0 and actual_exp > sanctioned:
        cost_overrun = round(((actual_exp - sanctioned) / sanctioned) * 100, 2)

    if cost_overrun > 30:
        score += 25.0
        reasons.append(f"High cost overrun: {cost_overrun:.1f}% beyond sanctioned budget")
    elif cost_overrun > 15:
        score += 15.0
        reasons.append(f"Moderate cost overrun: {cost_overrun:.1f}% over budget")
    elif cost_overrun > 5:
        score += 8.0
        reasons.append(f"Minor budget overrun: {cost_overrun:.1f}%")

    component('cost_overrun', 'Cost overrun', f'{cost_overrun:g}%',
        '>30%: +25; >15% to 30%: +15; >5% to 15%: +8; ≤5%: +0.', 25,
        project.get('cost_overrun_pct') is not None or (sanctioned > 0 and project.get('actual_expenditure') is not None))

    # 3. Project Delay (up to +25 points)
    delay_days = int(project.get('delay_days', 0) or 0)
    if delay_days > 120:
        score += 25.0
        reasons.append(f"Severe project delay of {delay_days} days")
    elif delay_days > 60:
        score += 15.0
        reasons.append(f"Moderate project delay of {delay_days} days")
    elif delay_days > 20:
        score += 8.0
        reasons.append(f"Minor project delay of {delay_days} days")

    component('delay', 'Recorded schedule delay', f'{delay_days} days',
        '>120 days: +25; >60 to 120: +15; >20 to 60: +8; ≤20: +0.', 25, project.get('delay_days') is not None)

    # 4. Physical-Financial Progress Gap (up to +10 points)
    phy_progress = float(project.get('physical_progress_pct', 0.0) or 0.0)
    fin_progress = float(project.get('financial_progress_pct', 0.0) or 0.0)
    raw_gap = project.get('physical_financial_gap_pct')
    gap_available = raw_gap is not None or (project.get('physical_progress_pct') is not None and project.get('financial_progress_pct') is not None)
    gap = float(raw_gap) if raw_gap is not None else fin_progress - phy_progress

    if gap_available and gap > 25:
        score += 10.0
        reasons.append(f"Large physical-financial gap ({gap:.1f} percentage points): Financial percentage significantly exceeds physical progress; verify the source percentage basis")
    elif gap_available and gap > 15:
        score += 6.0
        reasons.append(f"Moderate physical-financial gap ({gap:.1f} percentage points)")
    elif gap_available and gap > 5:
        score += 2.5
        reasons.append(f"Slight physical-financial mismatch ({gap:.1f} percentage points)")

    component('progress_gap', 'Financial minus physical progress', f'{gap:g} percentage points',
        '>25 points: +10; >15 to 25: +6; >5 to 15: +2.5; ≤5: +0.', 10,
        gap_available)

    # 5. Duplicate / overlap warning (up to +20 points)
    if duplicate_matches is not None:
        # Location-aware check: only pairs in the same district with extra evidence.
        if duplicate_matches:
            top = duplicate_matches[0]          # strongest match first
            if top['classification'] == 'Likely duplicate':
                score += 20.0
                reasons.append(
                    f"Likely duplicate of Project {top['other_work_id']} in the same district "
                    f"({top['evidence_score']:.0f}/100): {top['evidence']}")
            else:
                score += 10.0
                reasons.append(
                    f"Possible overlap with Project {top['other_work_id']} in the same district "
                    f"({top['evidence_score']:.0f}/100): {top['evidence']}")
    elif nlp_matches and len(nlp_matches) > 0:
        # Fallback: description-only match (ignores location)
        top_match = nlp_matches[0]
        score += 20.0
        reasons.append(f"Similar road work description detected with Project {top_match['matched_work_id']} ({top_match['similarity_pct']}%)")

    duplicate_value = 'No retained contextual match'
    if duplicate_matches:
        duplicate_value = f"{duplicate_matches[0]['classification']} — {duplicate_matches[0]['other_work_id']}"
    elif duplicate_matches is None and nlp_matches:
        duplicate_value = f"Wording-only fallback — {nlp_matches[0]['matched_work_id']}"
    component('duplicate', 'Similar / duplicate work evidence', duplicate_value,
        'Strongest contextual match only: likely duplicate +20; possible overlap +10; no match +0. Wording-only fallback +20 only when contextual results are unavailable.',
        20, duplicate_matches is not None or bool(nlp_matches))

    # 6. Low Bidder Competition / Single Bidder (+10 points)
    num_bidders = int(project.get('number_of_bidders', 0) or 0)
    if num_bidders == 1:
        score += 10.0
        reasons.append("Single bidder procurement (lack of competitive bidding)")

    component('bidders', 'Number of bidders', num_bidders,
        'Exactly one recorded bidder: +10; otherwise +0. Missing does not mean one bidder.',
        10, project.get('number_of_bidders') is not None)

    # 7. Expenditure Exceeds 1.8x Estimated Cost (+15 points)
    est_cost = float(project.get('estimated_cost', 0.0) or 0.0)
    if est_cost > 0 and actual_exp >= 1.8 * est_cost:
        score += 15.0
        reasons.append(f"Expenditure significantly exceeds original estimate (Rs. {actual_exp:,.0f} vs Rs. {est_cost:,.0f})")

    component('expenditure_ratio', 'Expenditure compared with original estimate',
        f'{actual_exp / est_cost:.4f} × estimated cost' if est_cost > 0 else None,
        'Actual expenditure ≥1.8 × estimated cost: +15; otherwise +0.', 15,
        est_cost > 0 and project.get('actual_expenditure') is not None)

    # Clamp score to 0 - 100
    final_score = round(min(100.0, max(0.0, score)), 1)

    # Classify Risk Level
    if final_score >= 70:
        risk_level = "HIGH"
    elif final_score >= 40:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    if not reasons:
        reasons.append("Project operating within normal cost, schedule, and progress parameters")

    return {
        'work_id': project['work_id'],
        'risk_score': final_score,
        'risk_level': risk_level,
        'risk_reason': " | ".join(reasons),
        'risk_breakdown': components,
        'uncapped_score': score,
        'cap_adjustment': final_score - score
    }

def run_risk_analysis_for_all(projects_data, ml_lookup, nlp_lookup, duplicate_lookup=None):
    """
    Computes risk score and explainable reasons for all projects.
    duplicate_lookup: {work_id: [matches]} from the location-aware duplicate check.
    When None, the old description-only NLP lookup is used instead.
    Returns list of records for risk_analysis table and lookup by work_id.
    """
    risk_records = []
    risk_lookup = {}

    for project in projects_data:
        w_id = project['work_id']
        ml_res = ml_lookup.get(w_id)
        nlp_matches = nlp_lookup.get(w_id, [])
        dup_matches = duplicate_lookup.get(w_id, []) if duplicate_lookup is not None else None

        risk_res = calculate_project_risk(project, ml_result=ml_res, nlp_matches=nlp_matches,
                                          duplicate_matches=dup_matches)
        risk_records.append(risk_res)
        risk_lookup[w_id] = risk_res

    return risk_records, risk_lookup
