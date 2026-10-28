import heapq
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def clean_description(text):
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def run_nlp_similarity_analysis(projects_data, threshold=0.70, max_pairs=1000):
    """
    Computes pairwise TF-IDF Cosine Similarity on road project descriptions using
    vectorized NumPy operations for ultra-fast execution even on 10,000+ rows.
    """
    if len(projects_data) < 2:
        return [], {}

    work_ids = [p['work_id'] for p in projects_data]
    descriptions = [clean_description(p.get('description', '')) for p in projects_data]

    valid_count = sum(1 for d in descriptions if len(d) > 0)
    if valid_count < 2:
        return [], {}

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        stop_words='english',
        min_df=1,
        max_features=2500
    )

    try:
        tfidf_matrix = vectorizer.fit_transform(descriptions)
    except ValueError as exc:
        if 'empty vocabulary' in str(exc): return [], {}
        raise
    # Keep the existing strongest-1000 behavior without allocating a full NxN array.
    heap=[]
    for start in range(0,len(work_ids),128):
        block=cosine_similarity(tfidf_matrix[start:start+128],tfidf_matrix)
        rr,cc=np.where(block>=threshold)
        global_rows=rr+start
        valid=cc>global_rows
        rr,cc,global_rows=rr[valid],cc[valid],global_rows[valid]
        values=block[rr,cc]
        order=np.lexsort((cc,global_rows,-values))[:max_pairs]
        for ix in order:
            item=(float(values[ix]),-int(global_rows[ix]),-int(cc[ix]))
            if len(heap)<max_pairs: heapq.heappush(heap,item)
            elif item>heap[0]: heapq.heapreplace(heap,item)
    chosen=sorted(heap,reverse=True)
    rows=np.array([-item[1] for item in chosen],dtype=int)
    cols=np.array([-item[2] for item in chosen],dtype=int)
    selected_scores=np.array([item[0] for item in chosen])

    similarity_records = []
    project_sim_lookup = {}

    if len(rows) > 0:
        scores = selected_scores
        # Sort indices by score descending
        sort_order = np.argsort(scores)[::-1]

        # Limit to top max_pairs to keep memory and DB lean
        if len(sort_order) > max_pairs:
            sort_order = sort_order[:max_pairs]

        for idx in sort_order:
            i = int(rows[idx])
            j = int(cols[idx])
            score = float(scores[idx])
            pct = round(score * 100, 1)
            w1 = work_ids[i]
            w2 = work_ids[j]

            status_text = f"Similar Project Detected ({pct}%)"
            similarity_records.append({
                'work_id_1': w1,
                'work_id_2': w2,
                'similarity_score': round(score, 4),
                'similarity_status': status_text
            })

            # Lookup for risk engine
            if w1 not in project_sim_lookup:
                project_sim_lookup[w1] = []
            project_sim_lookup[w1].append({
                'matched_work_id': w2,
                'similarity_pct': pct,
                'score': score
            })

            if w2 not in project_sim_lookup:
                project_sim_lookup[w2] = []
            project_sim_lookup[w2].append({
                'matched_work_id': w1,
                'similarity_pct': pct,
                'score': score
            })

    return similarity_records, project_sim_lookup
