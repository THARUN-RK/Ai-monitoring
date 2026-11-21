from __future__ import annotations
import numpy as np
from sklearn.ensemble import IsolationForest
from typing import Any
from app.aiops import (
    evaluate_aiops_telemetry,
    detect_cpu_anomaly,
    detect_memory_anomaly,
    detect_disk_anomaly,
    detect_network_anomaly,
    detect_security_anomaly,
)

FEATURES = [
    "cpu_utilization",
    "memory_utilization",
    "http_error_rate",
    "http_latency_p95_ms",
]

MODEL_VERSION = "cicada-aiops-hybrid-v2"


def train_model(historical_data: list[dict[str, Any]]) -> IsolationForest | None:
    """
    Train Isolation Forest using historical telemetry feature samples.
    """
    if len(historical_data) < 15:
        return None

    X = np.array(
        [
            [float(record[name]) for name in FEATURES]
            for record in historical_data
            if all(name in record for name in FEATURES)
        ],
        dtype=float,
    )

    if len(X) < 10:
        return None

    model = IsolationForest(
        n_estimators=100,
        contamination=0.04,
        random_state=42,
    )
    model.fit(X)
    return model


def score_feature_map(
    values: dict[str, float],
    model: IsolationForest | None = None,
    history_map: dict[str, list[float]] | None = None,
    failed_auth_count: int = 0,
    rejected_fields_count: int = 0,
) -> dict[str, Any]:
    """
    Hybrid AIOps scoring:
    1. Multi-variate Isolation Forest outlier detection.
    2. Dynamic statistical baseline & derivative rate-of-change detection.
    3. Comprehensive Explainable AI (XAI) output across CPU, Memory, Disk, Network, and Security.
    """
    # 1. Multi-variate Isolation Forest Scoring
    vector = np.array(
        [[
            float(values.get("cpu_utilization", 0.45)),
            float(values.get("memory_utilization", 0.55)),
            float(values.get("http_error_rate", 0.02)),
            float(values.get("http_latency_p95_ms", 180.0)),
        ]],
        dtype=float,
    )

    if model is None:
        rng = np.random.default_rng(42)
        baseline = rng.normal(
            loc=[0.42, 0.54, 0.018, 175.0],
            scale=[0.08, 0.08, 0.012, 35.0],
            size=(200, 4),
        )
        model = IsolationForest(
            contamination=0.04,
            random_state=42,
        )
        model.fit(baseline)

    iforest_pred = model.predict(vector)[0]
    iforest_score = float(model.decision_function(vector)[0])
    is_iforest_outlier = bool(iforest_pred == -1)

    # 2. Dynamic Statistical Baseline & Rate-of-Change Evaluation
    hist = history_map or {}
    aiops_eval = evaluate_aiops_telemetry(
        grouped_metrics=hist,
        latest_metrics=values,
        failed_auth_count=failed_auth_count,
        rejected_fields_count=rejected_fields_count,
    )

    anomalies = aiops_eval["anomalies"]
    overall_anomaly = is_iforest_outlier or aiops_eval["overall_anomaly"]

    # 3. Compile Primary Explanation & Recommendation
    if anomalies:
        primary = anomalies[0]
        explanation = primary["summary"]
        recommendation = primary["recommended_action"]
        probable_cause = primary["probable_cause"]
        severity = primary["severity"]
    elif is_iforest_outlier:
        explanation = (
            f"Multi-variate Isolation Forest outlier detected: metric cluster vector "
            f"deviated from multidimensional normal hyperplane (score: {iforest_score:.4f})."
        )
        probable_cause = "Non-linear correlation mismatch between system compute and latency percentiles."
        recommendation = "Investigate system thread pool contention and downstream request distribution."
        severity = "warning"
    else:
        explanation = "Telemetry cluster consistent with dynamic baseline operational models."
        probable_cause = "Normal steady-state workload."
        recommendation = "No corrective action required."
        severity = "info"

    # Compile signal attribution items
    signals = []
    for feat in FEATURES:
        val = float(values.get(feat, 0.0))
        base_info = aiops_eval["dynamic_baselines"].get(feat, {})
        thresh = base_info.get("upper", 0.80 if "rate" not in feat else 0.05)
        signals.append({
            "feature": feat,
            "value": round(val, 4),
            "baseline": base_info.get("mean", val),
            "threshold": thresh,
            "exceeded": val > thresh,
        })

    return {
        "status": "scored",
        "anomaly": overall_anomaly,
        "score": iforest_score,
        "severity": severity,
        "model_version": MODEL_VERSION,
        "explanation": explanation,
        "probable_cause": probable_cause,
        "recommendation": recommendation,
        "signals": signals,
        "anomalies": anomalies,
        "dynamic_baselines": aiops_eval["dynamic_baselines"],
        "security_risk_index": aiops_eval["security_risk_index"],
        "note": "AIOps Hybrid Engine: Dynamic Rolling Baselines + Isolation Forest + Explainable AI.",
    }
