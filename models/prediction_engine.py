"""
Delay & cost-overrun prediction learned from the uploaded dataset.

The model studies the projects in the uploaded file (the "past" records, whose
delay and cost overrun are already known), learns which project characteristics
lead to delays and overruns, and then estimates both for every project.

* Pure NumPy / pandas (no scikit-learn, no compiled extras), like ml_engine.py.
* Algorithm: gradient-boosted regression trees (histogram based).
* Honest evaluation: 5-fold cross-validation. Every project is predicted by a
  model that never saw that project, and accuracy is measured against the
  real recorded values and compared with a simple "always predict the median"
  baseline.
* Features are known before / during construction only. The outcome columns
  (delay_days, cost_overrun_pct, actual_expenditure, final_amount, status)
  are never used as inputs, so the model cannot just copy the answer.
"""
import math
from datetime import datetime

import numpy as np
import pandas as pd

NUMERIC_FEATURES = [
    'estimated_cost', 'sanctioned_amount', 'cost_per_km',
    'length_m', 'physical_progress_pct', 'financial_progress_pct',
]
CATEGORICAL_FEATURES = ['road_type', 'state']
MAX_CATEGORIES = 8            # most frequent categories kept per categorical column
# Track-record features: the average past outcome of the same vendor / district,
# learned only from training rows so the model never sees a project's own answer.
HISTORY_KEYS = [('vendor_id', 'vendor_track_record'), ('district', 'district_history')]
HISTORY_SMOOTHING = 5.0

DELAY_THRESHOLD_DAYS = 30     # same threshold the app uses for the "Delayed" status
OVERRUN_THRESHOLD_PCT = 15    # same threshold the dashboards highlight as a cost overrun
MIN_ROWS = 30                 # below this there is not enough history to learn from
N_FOLDS = 5

TARGETS = [
    # key, source column, threshold, label
    ('delay', 'delay_days', DELAY_THRESHOLD_DAYS, 'Delay (days)'),
    ('overrun', 'cost_overrun_pct', OVERRUN_THRESHOLD_PCT, 'Cost overrun (%)'),
]


# ---------------------------------------------------------------------------
# Gradient boosted trees (histogram based, squared-error loss)
# ---------------------------------------------------------------------------
class GradientBoostedTrees:
    def __init__(self, n_rounds=60, learning_rate=0.1, max_depth=3, n_bins=16,
                 min_leaf=10, subsample=0.8, seed=42):
        self.n_rounds = n_rounds
        self.lr = learning_rate
        self.max_depth = max_depth
        self.n_bins = n_bins
        self.min_leaf = min_leaf
        self.subsample = subsample
        self.seed = seed
        self.edges = []
        self.trees = []
        self.base = 0.0
        self.importance = None

    # --- binning -------------------------------------------------------
    def _fit_bins(self, X):
        self.edges = []
        qs = np.linspace(0, 1, self.n_bins + 1)[1:-1]
        for j in range(X.shape[1]):
            self.edges.append(np.unique(np.quantile(X[:, j], qs)))

    def _bin(self, X):
        Xb = np.empty(X.shape, dtype=np.int32)
        for j, e in enumerate(self.edges):
            Xb[:, j] = np.searchsorted(e, X[:, j], side='right')
        return Xb

    # --- tree building -------------------------------------------------
    def _build(self, Xb, r, depth):
        n, d = Xb.shape
        if depth >= self.max_depth or n < 2 * self.min_leaf:
            return float(r.mean()) if n else 0.0

        nb = self.n_bins
        flat = (Xb + self._offsets).ravel()
        cnt = np.bincount(flat, minlength=d * nb).reshape(d, nb).astype(float)
        sm = np.bincount(flat, weights=np.repeat(r, d), minlength=d * nb).reshape(d, nb)

        total = r.sum()
        cl = np.cumsum(cnt, axis=1)[:, :-1]
        sl = np.cumsum(sm, axis=1)[:, :-1]
        cr = n - cl
        sr = total - sl
        valid = (cl >= self.min_leaf) & (cr >= self.min_leaf)
        gain = np.where(
            valid,
            sl ** 2 / np.maximum(cl, 1.0) + sr ** 2 / np.maximum(cr, 1.0) - total ** 2 / n,
            -np.inf,
        )
        j, k = np.unravel_index(np.argmax(gain), gain.shape)
        best = gain[j, k]
        if not np.isfinite(best) or best <= 1e-12:
            return float(r.mean())

        self.importance[j] += best
        mask = Xb[:, j] <= k
        return (int(j), int(k),
                self._build(Xb[mask], r[mask], depth + 1),
                self._build(Xb[~mask], r[~mask], depth + 1))

    def _predict_tree(self, node, Xb, idx, out):
        if isinstance(node, float):
            out[idx] = node
            return
        j, k, left, right = node
        m = Xb[idx, j] <= k
        self._predict_tree(left, Xb, idx[m], out)
        self._predict_tree(right, Xb, idx[~m], out)

    # --- public API ----------------------------------------------------
    def fit(self, X, y):
        n, d = X.shape
        self._fit_bins(X)
        Xb = self._bin(X)
        self._offsets = (np.arange(d, dtype=np.int32) * self.n_bins)[None, :]
        self.importance = np.zeros(d)
        self.base = float(np.mean(y))
        pred = np.full(n, self.base)
        rng = np.random.RandomState(self.seed)
        self.trees = []
        for _ in range(self.n_rounds):
            resid = y - pred
            if self.subsample < 1.0:
                idx = rng.choice(n, size=max(2, int(n * self.subsample)), replace=False)
            else:
                idx = np.arange(n)
            tree = self._build(Xb[idx], resid[idx], 0)
            self.trees.append(tree)
            step = np.zeros(n)
            self._predict_tree(tree, Xb, np.arange(n), step)
            pred += self.lr * step
        return self

    def predict(self, X):
        Xb = self._bin(X)
        n = X.shape[0]
        pred = np.full(n, self.base)
        for tree in self.trees:
            step = np.zeros(n)
            self._predict_tree(tree, Xb, np.arange(n), step)
            pred += self.lr * step
        return pred


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------
def _num(df, col):
    if col in df.columns:
        s = pd.to_numeric(df[col], errors='coerce').fillna(0.0).values.astype(float)
        return np.nan_to_num(s, nan=0.0, posinf=0.0, neginf=0.0)
    return np.zeros(len(df), dtype=float)


def build_features(df):
    """Returns (X, feature_names). Only inputs known before the outcome."""
    cols, names = [], []
    for c in NUMERIC_FEATURES:
        cols.append(_num(df, c))
        names.append(c)

    sanctioned = _num(df, 'sanctioned_amount')
    safe_sanc = np.where(sanctioned > 0, sanctioned, 1.0)
    length = _num(df, 'length_m')
    safe_len = np.where(length > 0, length, 1.0)

    cols.append(np.where(sanctioned > 0, _num(df, 'tender_amount') / safe_sanc, 1.0))
    names.append('tender_to_sanction_ratio')
    cols.append(np.where(sanctioned > 0, _num(df, 'agreement_amount') / safe_sanc, 1.0))
    names.append('agreement_to_sanction_ratio')
    cols.append(np.where(length > 0, sanctioned / safe_len, 0.0))
    names.append('cost_per_meter')
    cols.append(_num(df, 'financial_progress_pct') - _num(df, 'physical_progress_pct'))
    names.append('progress_gap_pct')

    for c in CATEGORICAL_FEATURES:
        if c in df.columns:
            values = df[c].astype(str)
            for cat in values.value_counts().head(MAX_CATEGORIES).index:
                cols.append((values == cat).astype(float).values)
                names.append(f'{c} = {cat}')

    return np.column_stack(cols), names


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------
def _history_encode(keys_fit, y_fit, keys_apply):
    """Smoothed average outcome per group, learned from (keys_fit, y_fit)."""
    mean = float(np.mean(y_fit))
    stats = pd.Series(y_fit).groupby(np.asarray(keys_fit)).agg(['sum', 'count'])
    enc = (stats['sum'] + HISTORY_SMOOTHING * mean) / (stats['count'] + HISTORY_SMOOTHING)
    return pd.Series(np.asarray(keys_apply)).map(enc).fillna(mean).values.astype(float)


def _history_columns(keys, y, train_idx, apply_idx, inner_folds=5, seed=0):
    """
    Track-record columns for the training rows (computed with an inner split so a
    row never contributes to its own value) and for the rows to predict.
    """
    train_cols, apply_cols = [], []
    for key in keys:
        key = np.asarray(key)
        enc_train = np.zeros(len(train_idx))
        parts = np.array_split(np.random.RandomState(seed).permutation(len(train_idx)), inner_folds)
        for part in parts:
            fit_mask = np.ones(len(train_idx), dtype=bool)
            fit_mask[part] = False
            fit_rows = train_idx[fit_mask]
            enc_train[part] = _history_encode(key[fit_rows], y[fit_rows], key[train_idx[part]])
        train_cols.append(enc_train)
        apply_cols.append(_history_encode(key[train_idx], y[train_idx], key[apply_idx]))
    return np.column_stack(train_cols), np.column_stack(apply_cols)


def _cross_val_predict(X, y, history_keys, n_folds=N_FOLDS, seed=42):
    n = len(y)
    perm = np.random.RandomState(seed).permutation(n)
    folds = np.array_split(perm, n_folds)
    oof = np.zeros(n)
    importance = np.zeros(X.shape[1] + len(history_keys))
    # clip extreme targets for stable training only (evaluation uses real values)
    y_train_all = np.clip(y, 0, np.percentile(y, 99))
    for test_idx in folds:
        train_idx = np.setdiff1d(np.arange(n), test_idx)
        h_train, h_test = _history_columns(history_keys, y_train_all, train_idx, test_idx, seed=seed)
        model = GradientBoostedTrees(seed=seed).fit(
            np.hstack([X[train_idx], h_train]), y_train_all[train_idx])
        oof[test_idx] = model.predict(np.hstack([X[test_idx], h_test]))
        importance += model.importance
    return np.maximum(oof, 0.0), importance


def _decision_cutoff(pred, actual_pos_rate):
    """Flag the top share of projects (same share as really are delayed / overrun).
    A plain fixed threshold would almost never be crossed, because averaged
    predictions stay close to the middle."""
    if actual_pos_rate <= 0 or actual_pos_rate >= 1:
        return float('inf') if actual_pos_rate <= 0 else float('-inf')
    return float(np.percentile(pred, (1.0 - actual_pos_rate) * 100))


def _round(v, nd=3):
    return None if v is None else round(float(v), nd)


def _evaluate(y, pred, threshold):
    mae = float(np.mean(np.abs(y - pred)))
    rmse = float(math.sqrt(np.mean((y - pred) ** 2)))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - float(np.sum((y - pred) ** 2)) / ss_tot if ss_tot > 0 else 0.0
    baseline_mae = float(np.mean(np.abs(y - np.median(y))))
    improvement = (1 - mae / baseline_mae) * 100 if baseline_mae > 0 else 0.0

    actual_pos = y > threshold
    prevalence = float(np.mean(actual_pos))
    # Keep displayed review flags in the same units as the documented rule.
    # A prevalence percentile can collapse to zero on this master workbook,
    # incorrectly labelling zero-overrun estimates as "overrun likely".
    cutoff = float(threshold)
    pred_pos = pred > cutoff

    tp = int(np.sum(actual_pos & pred_pos))
    fp = int(np.sum(~actual_pos & pred_pos))
    fn = int(np.sum(actual_pos & ~pred_pos))
    tn = int(np.sum(~actual_pos & ~pred_pos))
    accuracy = (tp + tn) / len(y)
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall else (0.0 if precision is not None and recall is not None else None))
    lift = (precision / prevalence) if (precision is not None and prevalence > 0) else None

    # useful: clearly better than the median baseline, or the flagged group catches
    # at least a quarter of the real cases at 2x the chance rate
    if improvement >= 10 or (lift is not None and lift >= 2 and recall is not None and recall >= 0.25):
        verdict = 'useful'
    elif improvement > 0 or (lift is not None and lift > 1.2):
        verdict = 'weak'
    else:
        verdict = 'none'

    return {
        'mae': _round(mae), 'rmse': _round(rmse), 'r2': _round(r2),
        'baseline_mae': _round(baseline_mae),
        'mae_improvement_pct': _round(improvement, 1),
        'threshold': threshold,
        'decision_cutoff': _round(cutoff) if np.isfinite(cutoff) else None,
        'actual_positive_rate': _round(prevalence, 4),
        'accuracy': _round(accuracy, 4), 'precision': _round(precision, 4),
        'recall': _round(recall, 4), 'f1': _round(f1, 4), 'lift': _round(lift, 2),
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        'verdict': verdict,
    }, cutoff


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def run_prediction_analysis(projects_data):
    """
    Learns from the given projects and returns (records, summary).

    records : one dict per project  -> work_id, predicted_delay_days,
              predicted_overrun_pct, delay_likely, overrun_likely
    summary : JSON-friendly dict with model accuracy and top drivers
    """
    df = pd.DataFrame(projects_data) if isinstance(projects_data, list) else projects_data.copy()
    df = df.dropna(subset=['delay_days', 'cost_overrun_pct']).copy()
    n = len(df)
    # canonical order: the same projects always give the same result, whatever order they arrive in
    df = df.assign(_sort=df['work_id'].astype(str)).sort_values('_sort', kind='mergesort').drop(columns='_sort').reset_index(drop=True)
    if n < MIN_ROWS:
        return [], {'trained': False,
                    'message': f'Need at least {MIN_ROWS} projects to learn from; found {n}.'}

    X, names = build_features(df)
    history_keys = [df[col].astype(str).values if col in df.columns else np.zeros(n).astype(str)
                    for col, _ in HISTORY_KEYS]
    all_names = names + [label for _, label in HISTORY_KEYS]
    summary = {
        'trained': True,
        'model_name': 'Gradient Boosted Trees (NumPy)',
        'validation': f'{N_FOLDS}-fold cross-validation',
        'n_projects': int(n),
        'target_basis': 'Date-derived observed delay as of import/refresh date, including unfinished works; not final completion forecasts. Cost overrun derived from expenditure versus sanctioned amount.',
        'n_features': int(X.shape[1] + len(history_keys)),
        'trained_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    predictions, cutoffs = {}, {}
    for key, column, threshold, label in TARGETS:
        y = _num(df, column)
        pred, importance = _cross_val_predict(X, y, history_keys)
        metrics, cutoff = _evaluate(y, pred, threshold)
        metrics['label'] = label

        total_imp = importance.sum()
        order = np.argsort(importance)[::-1][:5]
        metrics['top_features'] = [
            {'name': all_names[i], 'share_pct': _round(importance[i] / total_imp * 100, 1)}
            for i in order if total_imp > 0 and importance[i] > 0
        ]
        summary[key] = metrics
        predictions[key] = pred
        cutoffs[key] = cutoff

    work_ids = df['work_id'].astype(str).tolist()
    records = []
    for i, wid in enumerate(work_ids):
        pd_days = float(predictions['delay'][i])
        po_pct = float(predictions['overrun'][i])
        records.append({
            'work_id': wid,
            'predicted_delay_days': round(pd_days, 1),
            'predicted_overrun_pct': round(po_pct, 2),
            'delay_likely': 1 if round(pd_days, 1) > cutoffs['delay'] else 0,
            'overrun_likely': 1 if round(po_pct, 2) > cutoffs['overrun'] else 0,
        })
    return records, summary
