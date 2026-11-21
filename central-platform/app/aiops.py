from __future__ import annotations
import math
import numpy as np
from datetime import datetime, timezone
from typing import Any


# -------------------------------------------------------------------------
# Dynamic Statistical Baseline & Anomaly Detection Utilities
# -------------------------------------------------------------------------

def compute_rolling_stats(values: list[float]) -> dict[str, float]:
    """
    Computes statistical baseline: mean, standard deviation, min, max,
    and dynamic upper/lower bounds using configurable sigma multiplier.
    """
    if not values:
        return {"mean": 0.0, "std": 0.0, "upper": 0.0, "lower": 0.0, "count": 0}

    arr = np.array(values, dtype=float)
    count = len(arr)
    mean = float(np.mean(arr))
    # Sample standard deviation (ddof=1) if enough samples, else population std
    std = float(np.std(arr, ddof=1)) if count > 1 else 0.0
    epsilon = 0.005
    effective_std = max(std, epsilon)

    return {
        "mean": round(mean, 4),
        "std": round(effective_std, 4),
        "upper": round(mean + 2.5 * effective_std, 4),
        "lower": round(max(0.0, mean - 2.5 * effective_std), 4),
        "count": count,
    }


def compute_z_score(current: float, mean: float, std: float) -> float:
    """Calculates z-score: number of standard deviations from dynamic baseline."""
    epsilon = 0.005
    return round((current - mean) / max(std, epsilon), 2)


def compute_deviation_pct(current: float, baseline: float) -> float:
    """Calculates percentage deviation from baseline."""
    epsilon = 0.001
    return round(((current - baseline) / max(abs(baseline), epsilon)) * 100.0, 1)


def compute_trend_slope(values: list[float]) -> float:
    """
    Calculates linear regression slope over chronological window.
    Positive slope indicates continuous growth/leak pattern.
    """
    n = len(values)
    if n < 3:
        return 0.0
    x = np.arange(n, dtype=float)
    y = np.array(values, dtype=float)
    # Slope = (n*sum(xy) - sum(x)*sum(y)) / (n*sum(x^2) - (sum(x))^2)
    denom = n * np.sum(x**2) - (np.sum(x))**2
    if abs(denom) < 1e-9:
        return 0.0
    slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / denom
    return float(slope)


# -------------------------------------------------------------------------
# Category-Specific Explainable Anomaly Detectors
# -------------------------------------------------------------------------

def detect_cpu_anomaly(
    history: list[float],
    current: float,
) -> dict[str, Any] | None:
    """
    Detects unusual CPU utilization, dynamic baseline deviations, and sudden spikes.
    """
    stats = compute_rolling_stats(history if history else [0.40, 0.45])
    mean = stats["mean"]
    std = stats["std"]
    z = compute_z_score(current, mean, std)
    dev_pct = compute_deviation_pct(current, mean)

    # Check for sudden single-cycle surge (spike derivative)
    prev_val = history[-1] if history else mean
    spike_delta = current - prev_val

    is_spike = spike_delta >= 0.25
    is_statistical_outlier = current > stats["upper"] or z >= 2.2
    is_critical_threshold = current >= 0.85

    if not (is_spike or is_statistical_outlier or is_critical_threshold):
        return None

    # Severity evaluation
    if current >= 0.88 or z >= 3.5 or spike_delta >= 0.40:
        severity = "critical"
        confidence = min(0.99, round(0.70 + 0.08 * abs(z), 2))
    else:
        severity = "warning"
        confidence = min(0.90, round(0.60 + 0.07 * abs(z), 2))

    summary = (
        f"Sudden CPU surge: current {(current*100):.1f}% exceeds dynamic baseline "
        f"({(mean*100):.1f}% ± {(std*100):.1f}%) by {dev_pct:+0.1f}% (z={z:+0.1f})."
    )
    if is_spike:
        summary += f" Instantaneous spike derivative: +{(spike_delta*100):.1f}% in 1 cycle."

    return {
        "metric_name": "cpu_utilization",
        "category": "cpu",
        "severity": severity,
        "current_value": round(current, 4),
        "baseline_value": round(mean, 4),
        "deviation_pct": dev_pct,
        "z_score": z,
        "confidence": confidence,
        "summary": summary,
        "probable_cause": (
            "Compute-intensive background tasks, runaway process loops, or unthrottled inference concurrency."
        ),
        "recommended_action": (
            "Scale horizontal service replicas, inspect high-CPU worker thread stacks, and configure request rate-limiting."
        ),
    }


def detect_memory_anomaly(
    history: list[float],
    current: float,
) -> dict[str, Any] | None:
    """
    Detects abnormal memory usage, static ceiling breach, and progressive memory leak patterns.
    """
    stats = compute_rolling_stats(history if history else [0.50, 0.55])
    mean = stats["mean"]
    std = stats["std"]
    z = compute_z_score(current, mean, std)
    dev_pct = compute_deviation_pct(current, mean)

    # Memory leak detection via positive monotonic trend
    recent_window = (history + [current])[-8:]
    slope = compute_trend_slope(recent_window)
    is_leaking = slope > 0.012 and len(recent_window) >= 4 and current > 0.70
    is_statistical_outlier = current > stats["upper"] or z >= 2.2
    is_critical_threshold = current >= 0.88

    if not (is_leaking or is_statistical_outlier or is_critical_threshold):
        return None

    if current >= 0.90 or (is_leaking and current >= 0.82):
        severity = "critical"
        confidence = min(0.98, round(0.72 + 0.08 * abs(z), 2))
    else:
        severity = "warning"
        confidence = min(0.89, round(0.62 + 0.07 * abs(z), 2))

    summary = (
        f"Abnormal memory consumption: current {(current*100):.1f}% exceeds rolling baseline "
        f"({(mean*100):.1f}% ± {(std*100):.1f}%) by {dev_pct:+0.1f}%."
    )
    if is_leaking:
        summary += f" Progressive allocation drift detected (growth slope: +{slope*100:.2f}%/cycle)."

    return {
        "metric_name": "memory_utilization",
        "category": "memory",
        "severity": severity,
        "current_value": round(current, 4),
        "baseline_value": round(mean, 4),
        "deviation_pct": dev_pct,
        "z_score": z,
        "confidence": confidence,
        "summary": summary,
        "probable_cause": (
            "Uncollected heap object references, database connection pool accumulation, or growing in-memory queues."
        ),
        "recommended_action": (
            "Profile process heap allocation, trigger garbage collection pass, and prepare graceful rolling container restart."
        ),
    }


def detect_disk_anomaly(
    history: list[float],
    current: float,
) -> dict[str, Any] | None:
    """
    Detects unusually high disk utilization, rapid consumption, and critical volume saturation.
    """
    stats = compute_rolling_stats(history if history else [0.42, 0.45])
    mean = stats["mean"]
    std = stats["std"]
    z = compute_z_score(current, mean, std)
    dev_pct = compute_deviation_pct(current, mean)

    is_critical_capacity = current >= 0.88
    is_warning_capacity = current >= 0.80 or current > stats["upper"]

    if not (is_critical_capacity or is_warning_capacity):
        return None

    severity = "critical" if current >= 0.88 else "warning"
    confidence = 0.96 if severity == "critical" else 0.85

    summary = (
        f"Storage volume pressure: disk utilization at {(current*100):.1f}% "
        f"(baseline: {(mean*100):.1f}%, deviation: {dev_pct:+0.1f}%)."
    )

    return {
        "metric_name": "disk_utilization",
        "category": "disk",
        "severity": severity,
        "current_value": round(current, 4),
        "baseline_value": round(mean, 4),
        "deviation_pct": dev_pct,
        "z_score": z,
        "confidence": confidence,
        "summary": summary,
        "probable_cause": (
            "Unrotated application audit logs, accumulated temporary payload buffers, or oversized persistent state."
        ),
        "recommended_action": (
            "Trigger automated log rotation, purge unreferenced local buffers, or expand volume storage quota."
        ),
    }


def detect_network_anomaly(
    latency_history: list[float],
    current_latency: float,
    error_history: list[float],
    current_error_rate: float,
) -> dict[str, Any] | None:
    """
    Detects network degradation: latency spikes, error rate surges, and packet degradation.
    """
    lat_stats = compute_rolling_stats(latency_history if latency_history else [150.0, 180.0])
    lat_mean = lat_stats["mean"]
    lat_std = lat_stats["std"]
    z_lat = compute_z_score(current_latency, lat_mean, lat_std)
    dev_pct = compute_deviation_pct(current_latency, lat_mean)

    is_latency_spike = current_latency > lat_stats["upper"] or current_latency >= 450.0
    is_error_spike = current_error_rate >= 0.05

    if not (is_latency_spike or is_error_spike):
        return None

    if current_latency >= 700.0 or current_error_rate >= 0.12 or z_lat >= 3.0:
        severity = "critical"
        confidence = min(0.99, round(0.75 + 0.08 * abs(z_lat), 2))
    else:
        severity = "warning"
        confidence = min(0.90, round(0.65 + 0.07 * abs(z_lat), 2))

    summary = (
        f"Network SLA degradation: p95 latency at {current_latency:.0f}ms exceeds baseline "
        f"({lat_mean:.0f}ms ± {lat_std:.0f}ms) by {dev_pct:+0.1f}%."
    )
    if is_error_spike:
        summary += f" Accompanying HTTP error rate: {(current_error_rate*100):.1f}%."

    return {
        "metric_name": "http_latency_p95_ms",
        "category": "network",
        "severity": severity,
        "current_value": round(current_latency, 1),
        "baseline_value": round(lat_mean, 1),
        "deviation_pct": dev_pct,
        "z_score": z_lat,
        "confidence": confidence,
        "summary": summary,
        "probable_cause": (
            "Upstream network routing saturation, downstream database locks, or microservice timeout cascaded failures."
        ),
        "recommended_action": (
            "Activate circuit breaker on degraded endpoints, verify upstream gateway health, and optimize query latency."
        ),
    }


def detect_security_anomaly(
    failed_attempts: int,
    rejected_fields_count: int = 0,
) -> dict[str, Any] | None:
    """
    Detects repeated authentication failures and calculates security risk indicators.
    CRITICAL PRIVACY RULE: Never export raw authentication logs, passwords, or usernames.
    Only aggregated statistical counts and risk indices are evaluated.
    """
    # Calculate security risk score (0 to 100)
    risk_score = min(100, int(failed_attempts * 18 + rejected_fields_count * 5))

    if failed_attempts < 3 and risk_score < 40:
        return None

    severity = "critical" if (failed_attempts >= 6 or risk_score >= 75) else "warning"
    confidence = min(0.99, round(0.70 + 0.05 * failed_attempts, 2))

    summary = (
        f"Security threat alert: {failed_attempts} repeated authentication challenges detected "
        f"(calculated security risk index: {risk_score}/100)."
    )
    if rejected_fields_count > 0:
        summary += f" Client-side filter intercepted {rejected_fields_count} secret injection attempts."

    return {
        "metric_name": "failed_auth_attempts",
        "category": "security",
        "severity": severity,
        "current_value": float(failed_attempts),
        "baseline_value": 0.0,
        "deviation_pct": round(failed_attempts * 100.0, 1),
        "z_score": round(failed_attempts / 1.5, 2),
        "confidence": confidence,
        "summary": summary,
        "probable_cause": (
            "Brute-force credential stuffing, expired API key cyclic retry, or unauthorized probing on protected endpoints."
        ),
        "recommended_action": (
            "Enforce IP address rate-limiting, issue temporary challenge throttle, and verify collector API credentials."
        ),
    }


# -------------------------------------------------------------------------
# Orchestrator: Comprehensive AIOps Evaluation
# -------------------------------------------------------------------------

def evaluate_aiops_telemetry(
    grouped_metrics: dict[str, list[float]],
    latest_metrics: dict[str, float],
    failed_auth_count: int = 0,
    rejected_fields_count: int = 0,
) -> dict[str, Any]:
    """
    Evaluates dynamic baselines and executes all 5 AIOps detection domains.
    Returns structured Explainable AI anomalies and dynamic baseline insights.
    """
    anomalies: list[dict[str, Any]] = []

    # 1. CPU Anomaly Detection
    cpu_hist = grouped_metrics.get("cpu_utilization", [])
    cpu_curr = latest_metrics.get("cpu_utilization", 0.45)
    cpu_anomaly = detect_cpu_anomaly(cpu_hist, cpu_curr)
    if cpu_anomaly:
        anomalies.append(cpu_anomaly)

    # 2. Memory Anomaly Detection
    mem_hist = grouped_metrics.get("memory_utilization", [])
    mem_curr = latest_metrics.get("memory_utilization", 0.55)
    mem_anomaly = detect_memory_anomaly(mem_hist, mem_curr)
    if mem_anomaly:
        anomalies.append(mem_anomaly)

    # 3. Disk Anomaly Detection
    disk_hist = grouped_metrics.get("disk_utilization", [])
    disk_curr = latest_metrics.get("disk_utilization", 0.42)
    disk_anomaly = detect_disk_anomaly(disk_hist, disk_curr)
    if disk_anomaly:
        anomalies.append(disk_anomaly)

    # 4. Network Anomaly Detection
    lat_hist = grouped_metrics.get("http_latency_p95_ms", [])
    lat_curr = latest_metrics.get("http_latency_p95_ms", 180.0)
    err_hist = grouped_metrics.get("http_error_rate", [])
    err_curr = latest_metrics.get("http_error_rate", 0.02)
    net_anomaly = detect_network_anomaly(lat_hist, lat_curr, err_hist, err_curr)
    if net_anomaly:
        anomalies.append(net_anomaly)

    # 5. Security Anomaly Detection
    sec_anomaly = detect_security_anomaly(failed_auth_count, rejected_fields_count)
    if sec_anomaly:
        anomalies.append(sec_anomaly)

    # Dynamic Baselines Summary
    baselines: dict[str, Any] = {}
    for metric_name, hist in grouped_metrics.items():
        if hist:
            baselines[metric_name] = compute_rolling_stats(hist)

    # Overall Status Determination
    has_critical = any(a["severity"] == "critical" for a in anomalies)
    has_warning = any(a["severity"] == "warning" for a in anomalies)

    overall_status = "critical" if has_critical else ("warning" if has_warning else "nominal")
    overall_anomaly = len(anomalies) > 0

    return {
        "status": overall_status,
        "overall_anomaly": overall_anomaly,
        "anomalies_count": len(anomalies),
        "anomalies": anomalies,
        "dynamic_baselines": baselines,
        "security_risk_index": min(100, int(failed_auth_count * 18 + rejected_fields_count * 5)),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
