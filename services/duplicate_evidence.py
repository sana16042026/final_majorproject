"""Explain the saved contextual match without rerunning or changing its score."""
def explain_duplicate_evidence(pair, first, second):
    reasons = [part.strip() for part in (pair.get('evidence') or '').split(';')]
    same_place = next((r.split(':', 1)[1].strip() for r in reasons if r.startswith('same named place:')), '')
    flags = [bool(same_place), 'same constituency' in reasons, 'same road type' in reasons,
             any(r.startswith('length within ') for r in reasons),
             any(r.startswith('estimated cost within ') for r in reasons)]
    maxima = [15, 10, 5, 10, 10]
    bonus = sum(m for m, flag in zip(maxima, flags) if flag)
    # The engine saves total at 1 decimal but cosine at 4 decimals. Subtracting
    # the exact integer bonuses preserves the original published rounding.
    text_points = round(float(pair['evidence_score']) - bonus, 1)
    rows = [dict(parameter='Description similarity', value=f"{float(pair['text_similarity'])*100:.2f}%",
                 rule='50 × cosine similarity; contribution includes the saved total rounding.',
                 points=text_points, maximum=50)]
    def difference(key):
        a,b=first.get(key),second.get(key)
        if a is None or b is None or float(a)<=0 or float(b)<=0:
            return 'Unavailable'
        return f'{abs(float(a)-float(b))/max(float(a),float(b))*100:.2f}% difference'
    values=[same_place or 'No retained shared-place evidence',
            f"{first.get('constituency') or 'Unavailable'} / {second.get('constituency') or 'Unavailable'}",
            f"{first.get('road_type') or 'Unavailable'} / {second.get('road_type') or 'Unavailable'}",
            difference('length_m'),difference('estimated_cost')]
    labels=['Shared named place','Same constituency','Same road type','Similar road length','Similar estimated cost']
    rules=['Shared named-place evidence: +15; otherwise 0.',
           'Same known constituency: +10; otherwise 0.',
           'Same known road type: +5; otherwise 0.',
           '|A − B| ÷ max(A, B) ≤5% with positive lengths: +10; otherwise 0.',
           '|A − B| ÷ max(A, B) ≤3% with positive estimates: +10; otherwise 0.']
    for label,value,rule,maximum,flag in zip(labels,values,rules,maxima,flags):
        rows.append(dict(parameter=label,value=value,rule=rule,points=maximum if flag else 0,maximum=maximum))
    for row in rows:row['status']='Awarded' if row['points'] else 'Not awarded'
    return dict(pair_id=pair['pair_id'],work_id_1=pair['work_id_1'],work_id_2=pair['work_id_2'],
                description_1=first['description'],description_2=second['description'],
                location=f"{first['district']}, {first['state']}",
                score=pair['evidence_score'],classification=pair['classification'],components=rows,
                total=round(sum(r['points'] for r in rows),1),
                note='The same state and district are eligibility requirements, not extra points. '
                     'At least 50% wording similarity and supporting place/road or length/cost evidence are required. '
                     'The saved score is rounded to one decimal; 80 or more is Likely duplicate, '
                     '55 to below 80 is Possible overlap. This is match evidence, not the project risk score or proof of duplication.')
