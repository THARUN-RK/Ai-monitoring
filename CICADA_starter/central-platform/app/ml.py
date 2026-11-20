import numpy as np
from sklearn.ensemble import IsolationForest

FEATURES = ["cpu_utilization", "memory_utilization", "http_error_rate", "http_latency_p95_ms"]

def score_feature_map(values: dict[str, float]):
    if not all(name in values for name in FEATURES):
        return {"status": "warmup", "anomaly": None, "reason": "Insufficient feature set"}

    vector = np.array([[values[name] for name in FEATURES]], dtype=float)
    # Demo baseline only. Replace with a persisted tenant/service baseline model.
    rng = np.random.default_rng(7)
    baseline = rng.normal(
        loc=[0.45, 0.55, 0.02, 180.0],
        scale=[0.12, 0.10, 0.015, 45.0],
        size=(250, 4),
    )
    model = IsolationForest(contamination=0.04, random_state=7)
    model.fit(baseline)
    return {
        "status": "scored",
        "anomaly": bool(model.predict(vector)[0] == -1),
        "score": float(model.decision_function(vector)[0]),
        "model_version": "demo-iforest-v0",
        "note": "Outlier signal only; not a root-cause diagnosis.",
    }
