import numpy as np
import pandas as pd
import math

FEATURE_COLS = [
    'estimated_cost',
    'sanctioned_amount',
    'actual_expenditure',
    'cost_overrun_pct',
    'delay_days',
    'length_m',
    'cost_per_km',
    'physical_progress_pct',
    'financial_progress_pct',
    'physical_financial_gap_pct'
]

def c_factor(n):
    """Average path length of unsuccessful searches in BST"""
    if n <= 1:
        return 0.0
    if n == 2:
        return 1.0
    return 2.0 * (math.log(n - 1) + 0.5772156649) - (2.0 * (n - 1) / float(n))

class FastIsolationTreeNode:
    def __init__(self, left=None, right=None, split_feature=None, split_value=None, size=0, is_leaf=False):
        self.left = left
        self.right = right
        self.split_feature = split_feature
        self.split_value = split_value
        self.size = size
        self.is_leaf = is_leaf

class FastIsolationTree:
    def __init__(self, max_depth, random_state=None):
        self.max_depth = max_depth
        self.rng = np.random.RandomState(random_state)
        self.root = None

    def fit(self, X):
        self.root = self._build_tree(X, depth=0)
        return self

    def _build_tree(self, X, depth):
        n_samples, n_features = X.shape
        if depth >= self.max_depth or n_samples <= 1:
            return FastIsolationTreeNode(size=n_samples, is_leaf=True)

        feat_idx = self.rng.randint(0, n_features)
        feat_min = X[:, feat_idx].min()
        feat_max = X[:, feat_idx].max()

        if feat_min == feat_max:
            return FastIsolationTreeNode(size=n_samples, is_leaf=True)

        split_val = self.rng.uniform(feat_min, feat_max)
        left_mask = X[:, feat_idx] < split_val
        right_mask = ~left_mask

        if left_mask.sum() == 0 or right_mask.sum() == 0:
            return FastIsolationTreeNode(size=n_samples, is_leaf=True)

        left_node = self._build_tree(X[left_mask], depth + 1)
        right_node = self._build_tree(X[right_mask], depth + 1)

        return FastIsolationTreeNode(
            left=left_node,
            right=right_node,
            split_feature=feat_idx,
            split_value=split_val,
            size=n_samples,
            is_leaf=False
        )

    def evaluate_paths_vectorized(self, X):
        """Vectorized traversal of all samples through the tree simultaneously."""
        n_samples = X.shape[0]
        lengths = np.zeros(n_samples, dtype=float)
        indices = np.arange(n_samples)

        def _traverse(node, curr_indices, depth):
            if len(curr_indices) == 0:
                return
            if node is None or node.is_leaf:
                sz = node.size if node else 1
                lengths[curr_indices] = float(depth) + c_factor(sz)
                return

            sub_x = X[curr_indices, node.split_feature]
            left_sel = sub_x < node.split_value
            right_sel = ~left_sel

            _traverse(node.left, curr_indices[left_sel], depth + 1)
            _traverse(node.right, curr_indices[right_sel], depth + 1)

        _traverse(self.root, indices, 0)
        return lengths

class RobustIsolationForest:
    """
    Vectorized, high-performance Isolation Forest (Liu, Ting, Zhou 2008).
    Processes 10,000+ samples in ~0.5 seconds without any C/Cython DLL dependencies.
    """
    def __init__(self, n_estimators=60, max_samples=256, contamination=0.15, random_state=42):
        self.n_estimators = n_estimators
        self.max_samples = max_samples
        self.contamination = contamination
        self.random_state = random_state
        self.trees = []
        self.subsample_size = 0

    def fit(self, X):
        n_samples = X.shape[0]
        self.subsample_size = min(self.max_samples, n_samples)
        max_depth = int(math.ceil(math.log2(max(self.subsample_size, 2))))
        rng = np.random.RandomState(self.random_state)

        self.trees = []
        for _ in range(self.n_estimators):
            subsample_indices = rng.choice(n_samples, size=self.subsample_size, replace=False)
            X_sub = X[subsample_indices]
            tree = FastIsolationTree(max_depth=max_depth, random_state=rng.randint(0, 100000))
            tree.fit(X_sub)
            self.trees.append(tree)
        return self

    def compute_anomaly_scores(self, X):
        if not self.trees:
            self.fit(X)

        n_samples = X.shape[0]
        total_paths = np.zeros(n_samples, dtype=float)

        for tree in self.trees:
            total_paths += tree.evaluate_paths_vectorized(X)

        avg_paths = total_paths / float(len(self.trees))
        c = c_factor(self.subsample_size)
        if c == 0:
            return np.full(n_samples, 0.5)

        # Anomaly score formula: s(x, n) = 2^(-E(h(x))/c(n))
        scores = np.power(2.0, -(avg_paths / c))
        return scores

    def fit_predict(self, X):
        self.fit(X)
        scores = self.compute_anomaly_scores(X)
        threshold = np.percentile(scores, (1.0 - self.contamination) * 100)
        preds = np.where(scores >= threshold, -1, 1)
        return preds, scores

def run_ml_anomaly_detection(projects_data, contamination=0.15):
    """
    Runs Isolation Forest Anomaly Detection on the numerical project features.
    Strictly excludes: anomaly_label, anomaly_type, risk_level_true.
    """
    if isinstance(projects_data, list):
        df = pd.DataFrame(projects_data)
    else:
        df = projects_data.copy()

    if len(df) == 0:
        return [], {}

    # Extract the numeric source and documented derived features and handle any NaN/inf
    X_vals = []
    for col in FEATURE_COLS:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors='coerce').fillna(0.0).values
            s = np.nan_to_num(s, nan=0.0, posinf=0.0, neginf=0.0)
        else:
            s = np.zeros(len(df), dtype=float)
        X_vals.append(s)

    X = np.column_stack(X_vals)

    # Normalize columns
    mins = X.min(axis=0)
    maxs = X.max(axis=0)
    ranges = maxs - mins
    ranges[ranges == 0] = 1.0
    X_norm = (X - mins) / ranges

    # Run Fast Isolation Forest
    model = RobustIsolationForest(
        n_estimators=50,
        max_samples=256,
        contamination=contamination,
        random_state=42
    )
    preds, raw_scores = model.fit_predict(X_norm)

    min_s = float(np.min(raw_scores))
    max_s = float(np.max(raw_scores))
    denom = max_s - min_s if (max_s - min_s) > 0 else 1.0
    norm_scores = (raw_scores - min_s) / denom

    ml_records = []
    ml_lookup = {}
    work_ids = df['work_id'].tolist()

    for idx, work_id in enumerate(work_ids):
        is_anomaly = 1 if preds[idx] == -1 else 0
        score_val = round(float(norm_scores[idx]), 4)

        record = {
            'work_id': str(work_id),
            'anomaly_score': score_val,
            'anomaly_detected': is_anomaly,
            'model_name': 'Isolation Forest'
        }
        ml_records.append(record)
        ml_lookup[str(work_id)] = record

    return ml_records, ml_lookup
