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

    is_anomaly = bool(prediction == -1)
    
    # Feature signal thresholds for explainability
    thresholds = {
        "cpu_utilization": 0.80,
        "memory_utilization": 0.85,
        "http_error_rate": 0.05,
        "http_latency_p95_ms": 500.0,
    }

    signals = []
    explanations = []
    recommendations = []

    for feat, thresh in thresholds.items():
        val = float(values.get(feat, 0.0))
        exceeded = val > thresh
        signals.append({
            "feature": feat,
            "value": round(val, 4),
            "threshold": thresh,
            "exceeded": exceeded,
        })
        if exceeded:
            explanations.append(f"{feat} at {val:.2f} exceeded nominal threshold ({thresh})")

    if values.get("cpu_utilization", 0) > 0.80:
        recommendations.append("Increase CPU allocation or scale service replicas.")
    if values.get("http_latency_p95_ms", 0) > 500:
        recommendations.append("Investigate upstream database locks or slow downstream dependencies.")
    if values.get("http_error_rate", 0) > 0.05:
        recommendations.append("Check application error logs for unhandled 5xx exceptions.")
    if not recommendations:
        recommendations.append("System operating within baseline variance.")

    explanation_text = "; ".join(explanations) if explanations else "Metric combination deviated from baseline clustering."

    return {
        "status": "scored",
        "anomaly": is_anomaly,
        "score": float(score),
        "model_version": MODEL_VERSION,
        "signals": signals,
        "explanation": explanation_text if is_anomaly else "Telemetry consistent with normal cluster.",
        "recommendation": "; ".join(recommendations) if is_anomaly else "No corrective action required.",
        "note": "Isolation Forest ML outlier detection with signal threshold attribution.",
    }