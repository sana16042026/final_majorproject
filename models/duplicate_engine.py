"""
Location-aware duplicate & overlap detection for road projects.

The older description-only check flags two projects whenever their wording is
similar, wherever they are. This engine only compares projects that are in the
SAME state and district, and then adds more evidence before calling a pair a
duplicate. Every flagged pair gets an evidence score (0-100) and a plain-language
list of reasons, so an auditor can see why it was flagged.

Evidence (maximum 100 points):
    50  description similarity (TF-IDF cosine, 0-1 scaled to 0-50)
    15  both descriptions name the same place (e.g. a village or landmark)
    10  same constituency
     5  same road type
    10  length within 5 %
    10  estimated cost within 3 %

    >= 80  "Likely duplicate"
    55-79  "Possible overlap"

A pair is only flagged if, besides similar wording, it either
    * names the same place AND has the same road type, or
    * matches on both length AND estimated cost.
Without this rule, generic wording such as "Construction of BT road work" would flag
unrelated projects, and two different road works in the same village would be flagged.

The dataset has no GPS coordinates, so "location" means state + district +
constituency + place names found in the descriptions.

Pure NumPy / pandas (no scikit-learn), like the other engines.
"""
import math
import re
from collections import Counter
from datetime import datetime

import numpy as np
import pandas as pd

STOPWORDS = {
    'of', 'in', 'at', 'the', 'and', 'to', 'from', 'near', 'with', 'for', 'a', 'an',
    'on', 'by', 'via', 'under', 'ward', 'no',
}
UNKNOWN_PLACES = {'', 'nan', 'none', 'general district', 'general state', 'general constituency'}

TEXT_CANDIDATE_MIN = 0.50     # descriptions less similar than this are never compared further
LIKELY_MIN = 80
POSSIBLE_MIN = 55
TOP_K_PER_PROJECT = 5         # strongest matches kept per project
MAX_PAIRS = 20000             # safety cap on stored pairs
BLOCK = 256                   # rows compared at once (keeps memory small)
MAX_CELLS = 60_000_000        # max size of one group's text matrix (rows x vocabulary)
PLACE_MAX_SHARE = 0.10        # a capitalised word used in more than 10 % of projects is not a place
LENGTH_TOLERANCE = 0.05
COST_TOLERANCE = 0.03

_WORD = re.compile(r'[a-z0-9]+')
_CAPITALISED = re.compile(r'\b[A-Z][a-z]{3,}\b')


def _tokens(text):
    return [t for t in _WORD.findall(text.lower())
            if t not in STOPWORDS and (len(t) > 1 or t.isdigit())]


def _capitalised_words(text):
    """Capitalised words except the first word of the description."""
    words = text.split()
    rest = ' '.join(words[1:]) if len(words) > 1 else ''
    return {w.lower() for w in _CAPITALISED.findall(rest)}


def _known(value):
    return str(value).strip().lower() not in UNKNOWN_PLACES


def _codes(values):
    """Integer code per distinct non-empty value; unknown values get -1 (never equal)."""
    mapping, out = {}, np.full(len(values), -1, dtype=np.int32)
    for i, v in enumerate(values):
        v = str(v).strip().lower()
        if v in UNKNOWN_PLACES:
            continue
        out[i] = mapping.setdefault(v, len(mapping))
    return out


def _num(df, col):
    if col in df.columns:
        s = pd.to_numeric(df[col], errors='coerce').fillna(0.0).values.astype(float)
        return np.nan_to_num(s, nan=0.0, posinf=0.0, neginf=0.0)
    return np.zeros(len(df))


def run_duplicate_analysis(projects_data):
    """
    Returns (records, summary).

    records : one dict per flagged pair -> work_id_1, work_id_2, text_similarity,
              evidence_score, classification, evidence
    summary : JSON-friendly dict with counts
    """
    df = pd.DataFrame(projects_data) if isinstance(projects_data, list) else projects_data.copy()
    n = len(df)
    # canonical order: the same projects always give the same result, whatever order they arrive in
    df = df.assign(_sort=df['work_id'].astype(str)).sort_values('_sort', kind='mergesort').drop(columns='_sort').reset_index(drop=True)
    empty = {'trained': False}
    if n < 2:
        return [], {**empty, 'message': 'Need at least 2 projects.'}

    work_ids = df['work_id'].astype(str).values
    descriptions = (df['description'].fillna('').astype(str).values
                    if 'description' in df.columns else np.array([''] * n))
    states = df['state'].astype(str).values if 'state' in df.columns else np.array([''] * n)
    districts = df['district'].astype(str).values if 'district' in df.columns else np.array([''] * n)
    constituency = _codes(df['constituency'].astype(str).values) if 'constituency' in df.columns else np.full(n, -1)
    road_type = _codes(df['road_type'].astype(str).values) if 'road_type' in df.columns else np.full(n, -1)
    length = _num(df, 'length_m')
    cost = _num(df, 'estimated_cost')

    token_lists = [_tokens(d) for d in descriptions]

    # global inverse document frequency (rare words count more)
    doc_freq = Counter()
    for toks in token_lists:
        doc_freq.update(set(toks))
    idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in doc_freq.items()}

    # place names: capitalised words that are not generic (not used by many projects)
    cap_sets = [_capitalised_words(d) for d in descriptions]
    cap_freq = Counter()
    for s in cap_sets:
        cap_freq.update(s)
    max_df = max(2, int(PLACE_MAX_SHARE * n))
    place_sets = [{w for w in s if 2 <= cap_freq[w] <= max_df} for s in cap_sets]
    place_vocab_size = len({w for s in place_sets for w in s})

    # group by location: only projects in the same state AND district are compared
    groups, unknown_location = {}, 0
    for i in range(n):
        if not (_known(states[i]) and _known(districts[i])):
            unknown_location += 1
            continue
        groups.setdefault((str(states[i]).strip().lower(), str(districts[i]).strip().lower()), []).append(i)

    pairs = []   # (score, text_sim, i, j) with i, j global indexes
    groups_compared = 0
    for members in groups.values():
        g = len(members)
        if g < 2:
            continue
        groups_compared += 1
        members = np.array(members)

        # --- text matrix for this location ---
        local_df = Counter()
        for i in members:
            local_df.update(set(token_lists[i]))
        vocab = [t for t, _ in local_df.most_common(max(50, MAX_CELLS // g))]
        index = {t: k for k, t in enumerate(vocab)}
        X = np.zeros((g, len(vocab)), dtype=np.float32)
        for r, i in enumerate(members):
            for t, c in Counter(token_lists[i]).items():
                k = index.get(t)
                if k is not None:
                    X[r, k] = (1.0 + math.log(c)) * idf.get(t, 1.0)
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        X /= norms

        # --- named-place matrix ---
        place_index = {}
        for i in members:
            for w in place_sets[i]:
                place_index.setdefault(w, len(place_index))
        P = np.zeros((g, len(place_index)), dtype=np.float32)
        for r, i in enumerate(members):
            for w in place_sets[i]:
                P[r, place_index[w]] = 1.0

        c_g, rt_g, len_g, cost_g = constituency[members], road_type[members], length[members], cost[members]

        for r0 in range(0, g, BLOCK):
            r1 = min(g, r0 + BLOCK)
            text = X[r0:r1] @ X.T
            rows = np.arange(r0, r1)[:, None]
            cols = np.arange(g)[None, :]
            valid = (cols > rows) & (text >= TEXT_CANDIDATE_MIN)
            if not valid.any():
                continue

            same_place = ((P[r0:r1] @ P.T) > 0) if P.shape[1] else np.zeros(text.shape, dtype=bool)
            cb = c_g[r0:r1][:, None]
            same_constituency = (cb == c_g[None, :]) & (cb >= 0)
            rb = rt_g[r0:r1][:, None]
            same_road = (rb == rt_g[None, :]) & (rb >= 0)
            la, lb = len_g[r0:r1][:, None], len_g[None, :]
            length_close = (la > 0) & (lb > 0) & (np.abs(la - lb) <= LENGTH_TOLERANCE * np.maximum(la, lb))
            ca, cbb = cost_g[r0:r1][:, None], cost_g[None, :]
            cost_close = (ca > 0) & (cbb > 0) & (np.abs(ca - cbb) <= COST_TOLERANCE * np.maximum(ca, cbb))

            # besides wording: same named place + same road type, OR length AND cost both match
            valid &= (same_place & same_road) | (length_close & cost_close)
            if not valid.any():
                continue

            score = (50.0 * text + 15.0 * same_place + 10.0 * same_constituency + 5.0 * same_road
                     + 10.0 * length_close + 10.0 * cost_close)
            score = np.where(valid, score, -1.0)

            k = min(TOP_K_PER_PROJECT, g)
            top = np.argpartition(-score, k - 1, axis=1)[:, :k] if g > k else np.tile(np.arange(g), (r1 - r0, 1))
            for local_row in range(r1 - r0):
                for col in top[local_row]:
                    s = score[local_row, col]
                    if s >= POSSIBLE_MIN:
                        pairs.append((float(s), float(text[local_row, col]),
                                      int(members[r0 + local_row]), int(members[col])))

    pairs.sort(key=lambda p: (-p[0], p[2], p[3]))
    pairs = pairs[:MAX_PAIRS]

    records = []
    for score, text_sim, i, j in pairs:
        reasons = [f"description {text_sim:.0%} similar", f"same district ({str(districts[i]).strip()})"]
        shared = sorted(place_sets[i] & place_sets[j])
        if shared:
            reasons.append("same named place: " + ", ".join(w.title() for w in shared[:3]))
        if constituency[i] >= 0 and constituency[i] == constituency[j]:
            reasons.append("same constituency")
        if road_type[i] >= 0 and road_type[i] == road_type[j]:
            reasons.append("same road type")
        if length[i] > 0 and length[j] > 0:
            d = abs(length[i] - length[j]) / max(length[i], length[j])
            if d <= LENGTH_TOLERANCE:
                reasons.append(f"length within {d:.0%}")
        if cost[i] > 0 and cost[j] > 0:
            d = abs(cost[i] - cost[j]) / max(cost[i], cost[j])
            if d <= COST_TOLERANCE:
                reasons.append(f"estimated cost within {d:.0%}")
        records.append({
            'work_id_1': work_ids[i], 'work_id_2': work_ids[j],
            'text_similarity': round(text_sim, 4),
            'evidence_score': round(score, 1),
            'classification': 'Likely duplicate' if score >= LIKELY_MIN else 'Possible overlap',
            'evidence': '; '.join(reasons),
        })

    involved = {r['work_id_1'] for r in records} | {r['work_id_2'] for r in records}
    summary = {
        'trained': True,
        'method': 'Same district + description similarity + named place, constituency, length and cost',
        'n_projects': int(n),
        'locations_compared': int(groups_compared),
        'projects_without_location': int(unknown_location),
        'place_names_found': int(place_vocab_size),
        'n_pairs': len(records),
        'likely_duplicates': sum(1 for r in records if r['classification'] == 'Likely duplicate'),
        'possible_overlaps': sum(1 for r in records if r['classification'] == 'Possible overlap'),
        'projects_involved': len(involved),
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    return records, summary


def build_duplicate_lookup(records):
    """{work_id: [matches, strongest first]} for the risk engine. Both projects of a pair get an entry."""
    lookup = {}
    for r in records:      # records are already sorted by evidence score (high to low)
        for me, other in ((r['work_id_1'], r['work_id_2']), (r['work_id_2'], r['work_id_1'])):
            lookup.setdefault(me, []).append({
                'other_work_id': other,
                'classification': r['classification'],
                'evidence_score': r['evidence_score'],
                'evidence': r['evidence'],
            })
    return lookup
