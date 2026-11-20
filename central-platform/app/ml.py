import numpy as np
from sklearn.ensemble import IsolationForest

FEATURES = [
    "cpu_utilization",
    "memory_utilization",
    "http_error_rate",
    "http_latency_p95_ms",
]

MODEL_VERSION = "cicada-iforest-v1"


def train_model(historical_data):
    """
    Train Isolation Forest using historical telemetry.
    """

    if len(historical_data) < 20:
        return None

    X = np.array(
        [
            [float(record[name]) for name in FEATURES]
            for record in historical_data
        ],
        dtype=float,
    )

    model = IsolationForest(
        n_estimators=100,
        contamination=0.04,
        random_state=42,
    )

    model.fit(X)

    return model


def score_feature_map(values: dict[str, float], model=None):

    if not all(name in values for name in FEATURES):
        return {
            "status": "warmup",
            "anomaly": None,
            "reason": "Insufficient feature set",
        }

    vector = np.array(
        [[float(values[name]) for name in FEATURES]],
        dtype=float,
    )

    # Temporary demo fallback.
    # Production scoring should use a model trained on historical telemetry.
    if model is None:
        rng = np.random.default_rng(7)

        baseline = rng.normal(
            loc=[0.45, 0.55, 0.02, 180.0],
            scale=[0.12, 0.10, 0.015, 45.0],
            size=(250, 4),
        )

        model = IsolationForest(
            contamination=0.04,
            random_state=42,
        )

        model.fit(baseline)

    prediction = model.predict(vector)[0]
    score = model.decision_function(vector)[0]

    return {
        "status": "scored",
        "anomaly": bool(prediction == -1),
        "score": float(score),
        "model_version": MODEL_VERSION,
        "note": "Outlier signal only; not a root-cause diagnosis.",
    }