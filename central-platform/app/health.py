from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.models import HealthTransitionRecord, CollectorRecord, MetricRecord, AnomalyRecord


class HealthState:
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


STATE_RANKS = {
    HealthState.EXCELLENT: 1,
    HealthState.GOOD: 2,
    HealthState.FAIR: 3,
    HealthState.POOR: 4,
}


def worst_state(*states: str) -> str:
    """Returns the most degraded (highest rank) state among all inputs."""
    valid = [s for s in states if s in STATE_RANKS]
    if not valid:
        return HealthState.POOR
    return max(valid, key=lambda s: STATE_RANKS[s])


@dataclass
class MetricThresholdConfig:
    excellent_max: float
    good_max: float
    fair_max: float  # >= fair_max is POOR

    def to_dict(self) -> dict[str, float]:
        return {
            "excellent_max": self.excellent_max,
            "good_max": self.good_max,
            "fair_max": self.fair_max,
        }


@dataclass
class HealthConfig:
    """Configurable thresholds for 4-state health classification engine."""
    cpu_utilization: MetricThresholdConfig = field(
        default_factory=lambda: MetricThresholdConfig(excellent_max=0.60, good_max=0.75, fair_max=0.88)
    )
    memory_utilization: MetricThresholdConfig = field(
        default_factory=lambda: MetricThresholdConfig(excellent_max=0.65, good_max=0.80, fair_max=0.90)
    )
    disk_utilization: MetricThresholdConfig = field(
        default_factory=lambda: MetricThresholdConfig(excellent_max=0.70, good_max=0.80, fair_max=0.90)
    )
    http_latency_p95_ms: MetricThresholdConfig = field(
        default_factory=lambda: MetricThresholdConfig(excellent_max=250.0, good_max=450.0, fair_max=750.0)
    )
    http_error_rate: MetricThresholdConfig = field(
        default_factory=lambda: MetricThresholdConfig(excellent_max=0.01, good_max=0.03, fair_max=0.08)
    )
    freshness_seconds: MetricThresholdConfig = field(
        default_factory=lambda: MetricThresholdConfig(excellent_max=15.0, good_max=30.0, fair_max=60.0)
    )
    collector_stale_warning_seconds: float = 30.0
    collector_stale_critical_seconds: float = 60.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HealthConfig:
        config = cls()
        for key in ["cpu_utilization", "memory_utilization", "disk_utilization", "http_latency_p95_ms", "http_error_rate", "freshness_seconds"]:
            if key in data and isinstance(data[key], dict):
                setattr(config, key, MetricThresholdConfig(
                    excellent_max=data[key].get("excellent_max", getattr(config, key).excellent_max),
                    good_max=data[key].get("good_max", getattr(config, key).good_max),
                    fair_max=data[key].get("fair_max", getattr(config, key).fair_max),
                ))
        if "collector_stale_warning_seconds" in data:
            config.collector_stale_warning_seconds = float(data["collector_stale_warning_seconds"])
        if "collector_stale_critical_seconds" in data:
            config.collector_stale_critical_seconds = float(data["collector_stale_critical_seconds"])
        return config


# -------------------------------------------------------------------------
# Evaluation Core
# -------------------------------------------------------------------------

def evaluate_single_metric(
    metric_name: str,
    value: float,
    unit: str,
    config: HealthConfig,
) -> dict[str, Any]:
    """
    Evaluates an individual hardware or application metric against configurable thresholds.
    Returns dict with state (EXCELLENT, GOOD, FAIR, POOR), threshold_applied, and explanation reason.
    """
    # Lookup threshold config for known metrics
    threshold_cfg: Optional[MetricThresholdConfig] = getattr(config, metric_name, None)

    if threshold_cfg is None:
        # Default fallback for arbitrary numeric metrics
        if "latency" in metric_name:
            threshold_cfg = config.http_latency_p95_ms
        elif "error" in metric_name:
            threshold_cfg = config.http_error_rate
        else:
            threshold_cfg = config.cpu_utilization

    val = float(value)
    thresh = threshold_cfg.to_dict()

    human_name = metric_name.replace("_", " ").title()
    formatted_val = f"{val * 100:.1f}%" if unit == "ratio" else f"{val:.1f} {unit}"

    if val < threshold_cfg.excellent_max:
        state = HealthState.EXCELLENT
        reason = f"{human_name} ({formatted_val}) is optimal (< {threshold_cfg.excellent_max})."
    elif val < threshold_cfg.good_max:
        state = HealthState.GOOD
        reason = f"{human_name} ({formatted_val}) is within nominal operating range (< {threshold_cfg.good_max})."
    elif val < threshold_cfg.fair_max:
        state = HealthState.FAIR
        reason = f"{human_name} ({formatted_val}) is elevated above normal threshold ({threshold_cfg.good_max}); requires attention."
    else:
        state = HealthState.POOR
        reason = f"{human_name} ({formatted_val}) reached critical degradation (>= {threshold_cfg.fair_max}); immediate intervention required."

    return {
        "metric_name": metric_name,
        "current_value": val,
        "unit": unit,
        "state": state,
        "threshold_applied": thresh,
        "reason": reason,
    }


def evaluate_collector_availability(
    collector: Optional[CollectorRecord | dict[str, Any]],
    now: datetime,
    config: HealthConfig,
) -> dict[str, Any]:
    """
    Evaluates Tier 1 local collector fleet availability and heartbeat status.
    """
    if not collector:
        return {
            "collector_id": "none",
            "status": "offline",
            "last_heartbeat": None,
            "freshness_seconds": None,
            "state": HealthState.POOR,
            "reason": "Collector offline: No registered collector found for this tenant.",
        }

    c_id = collector.collector_id if hasattr(collector, "collector_id") else collector.get("collector_id", "unknown")
    status = collector.status if hasattr(collector, "status") else collector.get("status", "unknown")
    lh = collector.last_heartbeat if hasattr(collector, "last_heartbeat") else collector.get("last_heartbeat")

    if status.lower() in ("offline", "inactive", "disconnected"):
        return {
            "collector_id": c_id,
            "status": "offline",
            "last_heartbeat": lh.isoformat() if isinstance(lh, datetime) else str(lh) if lh else None,
            "freshness_seconds": None,
            "state": HealthState.POOR,
            "reason": f"Collector '{c_id}' status marked offline.",
        }

    if not lh:
        return {
            "collector_id": c_id,
            "status": status,
            "last_heartbeat": None,
            "freshness_seconds": None,
            "state": HealthState.POOR,
            "reason": f"Collector '{c_id}' has never transmitted a heartbeat.",
        }

    if isinstance(lh, str):
        try:
            lh_dt = datetime.fromisoformat(lh.replace("Z", "+00:00"))
        except Exception:
            lh_dt = now
    else:
        lh_dt = lh

    if lh_dt.tzinfo is None:
        lh_dt = lh_dt.replace(tzinfo=timezone.utc)

    age_sec = max(0.0, (now - lh_dt).total_seconds())

    if age_sec >= config.collector_stale_critical_seconds:
        state = HealthState.POOR
        reason = f"Collector '{c_id}' heartbeat missing ({age_sec:.1f}s ago >= {config.collector_stale_critical_seconds}s limit); collector considered offline."
    elif age_sec >= config.collector_stale_warning_seconds:
        state = HealthState.FAIR
        reason = f"Collector '{c_id}' heartbeat delayed ({age_sec:.1f}s ago >= {config.collector_stale_warning_seconds}s warning threshold)."
    else:
        state = HealthState.EXCELLENT
        reason = f"Collector '{c_id}' online and active (last heartbeat {age_sec:.1f}s ago)."

    return {
        "collector_id": c_id,
        "status": status,
        "last_heartbeat": lh_dt.isoformat(),
        "freshness_seconds": round(age_sec, 2),
        "state": state,
        "reason": reason,
    }


def evaluate_telemetry_freshness(
    last_observed_at: Optional[datetime | str],
    now: datetime,
    config: HealthConfig,
) -> dict[str, Any]:
    """
    Evaluates telemetry freshness and downgrades health when telemetry becomes stale or missing.
    """
    if last_observed_at is None:
        return {
            "last_telemetry_at": None,
            "age_seconds": None,
            "state": HealthState.POOR,
            "reason": "Missing telemetry: No telemetry records received from customer environment.",
        }

    if isinstance(last_observed_at, str):
        try:
            last_dt = datetime.fromisoformat(last_observed_at.replace("Z", "+00:00"))
        except Exception:
            last_dt = now
    else:
        last_dt = last_observed_at

    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)

    age_sec = max(0.0, (now - last_dt).total_seconds())
    cfg = config.freshness_seconds

    if age_sec < cfg.excellent_max:
        state = HealthState.EXCELLENT
        reason = f"Telemetry stream fresh ({age_sec:.1f}s ago < {cfg.excellent_max}s)."
    elif age_sec < cfg.good_max:
        state = HealthState.GOOD
        reason = f"Telemetry stream active ({age_sec:.1f}s ago < {cfg.good_max}s)."
    elif age_sec < cfg.fair_max:
        state = HealthState.FAIR
        reason = f"Telemetry stream is stale ({age_sec:.1f}s ago >= {cfg.good_max}s). Health downgraded due to delayed reporting."
    else:
        state = HealthState.POOR
        reason = f"Telemetry stream expired or missing ({age_sec:.1f}s ago >= {cfg.fair_max}s). Critical observability loss."

    return {
        "last_telemetry_at": last_dt.isoformat(),
        "age_seconds": round(age_sec, 2),
        "state": state,
        "reason": reason,
    }


def evaluate_aiops_anomalies(
    active_anomalies: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Evaluates active AIOps anomalies and correlates them with health classification.
    """
    active_count = len(active_anomalies)
    crit_count = sum(1 for a in active_anomalies if a.get("severity") == "critical")
    warn_count = sum(1 for a in active_anomalies if a.get("severity") == "warning")

    if crit_count > 0:
        state = HealthState.POOR
        crit_metrics = [a.get("metric_name", "unknown") for a in active_anomalies if a.get("severity") == "critical"]
        reason = f"AIOps engine detected {crit_count} critical operational anomalies ({', '.join(crit_metrics)})."
        max_sev = "critical"
    elif warn_count > 0:
        state = HealthState.FAIR
        warn_metrics = [a.get("metric_name", "unknown") for a in active_anomalies if a.get("severity") == "warning"]
        reason = f"AIOps engine detected {warn_count} warning anomalies ({', '.join(warn_metrics)})."
        max_sev = "warning"
    else:
        state = HealthState.EXCELLENT
        reason = "AIOps model reports nominal infrastructure baselines without anomalies."
        max_sev = "none"

    return {
        "active_count": active_count,
        "critical_count": crit_count,
        "warning_count": warn_count,
        "max_severity": max_sev,
        "state": state,
        "reason": reason,
    }


def evaluate_system_health(
    tenant_id: str,
    metrics_map: dict[str, tuple[float, str]],  # {metric_name: (value, unit)}
    collector: Optional[CollectorRecord | dict[str, Any]] = None,
    last_telemetry_at: Optional[datetime | str] = None,
    active_anomalies: Optional[list[dict[str, Any]]] = None,
    config: Optional[HealthConfig] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """
    Comprehensive four-state health classification engine:
    1. Evaluates CPU, memory, disk, latency, and error rate.
    2. Evaluates collector availability and heartbeats.
    3. Evaluates telemetry freshness and detects stale/missing telemetry.
    4. Incorporates AIOps anomaly information.
    5. Returns unified 4-state overall health with explainability reasons.
    """
    if config is None:
        config = HealthConfig()
    if now is None:
        now = datetime.now(timezone.utc)
    if active_anomalies is None:
        active_anomalies = []

    # 1. Evaluate individual metrics
    metric_evals: list[dict[str, Any]] = []
    for m_name, (m_val, m_unit) in metrics_map.items():
        eval_res = evaluate_single_metric(m_name, m_val, m_unit, config)
        metric_evals.append(eval_res)

    # 2. Evaluate collector availability
    col_eval = evaluate_collector_availability(collector, now, config)

    # 3. Evaluate telemetry freshness (detect stale or missing telemetry)
    fresh_eval = evaluate_telemetry_freshness(last_telemetry_at, now, config)

    # 4. Evaluate AIOps anomalies
    anomaly_eval = evaluate_aiops_anomalies(active_anomalies)

    # 5. Determine overall health (worst-case state hierarchy)
    all_states: list[str] = [m["state"] for m in metric_evals]
    all_states.append(col_eval["state"])
    all_states.append(fresh_eval["state"])
    all_states.append(anomaly_eval["state"])

    overall = worst_state(*all_states)

    # Collect contributing reasons for non-excellent items
    contributing_reasons: list[str] = []
    for m in metric_evals:
        if m["state"] != HealthState.EXCELLENT:
            contributing_reasons.append(m["reason"])
    if col_eval["state"] != HealthState.EXCELLENT:
        contributing_reasons.append(col_eval["reason"])
    if fresh_eval["state"] != HealthState.EXCELLENT:
        contributing_reasons.append(fresh_eval["reason"])
    if anomaly_eval["state"] != HealthState.EXCELLENT:
        contributing_reasons.append(anomaly_eval["reason"])

    if not contributing_reasons:
        summary_reason = "All infrastructure telemetry, collector heartbeats, and AIOps baselines are operating in EXCELLENT status."
    else:
        summary_reason = f"System health is {overall}: " + "; ".join(contributing_reasons)

    return {
        "tenant_id": tenant_id,
        "overall_health": overall,
        "evaluated_at": now.isoformat(),
        "summary_reason": summary_reason,
        "reasons": contributing_reasons if contributing_reasons else [summary_reason],
        "metrics": metric_evals,
        "collector": col_eval,
        "freshness": fresh_eval,
        "anomalies": anomaly_eval,
    }


# -------------------------------------------------------------------------
# Transition History Persistence
# -------------------------------------------------------------------------

def record_transition_if_changed(
    db: Session,
    tenant_id: str,
    evaluation: dict[str, Any],
    force: bool = False,
) -> Optional[HealthTransitionRecord]:
    """
    Records every health-state transition into the database with UTC timestamps
    and human-readable explanations of why the state changed.
    """
    current_health = evaluation["overall_health"]

    # Query latest transition for tenant
    stmt = (
        select(HealthTransitionRecord)
        .where(HealthTransitionRecord.tenant_id == tenant_id)
        .order_by(desc(HealthTransitionRecord.id))
        .limit(1)
    )
    latest = db.execute(stmt).scalar_one_or_none()

    from_state = "INITIAL" if latest is None else latest.to_state

    # Only record if state actually changed or forced
    if latest is not None and latest.to_state == current_health and not force:
        return None

    # Construct snapshot of current evaluation
    metrics_snapshot = json.dumps({
        "metrics": {m["metric_name"]: {"value": m["current_value"], "state": m["state"]} for m in evaluation["metrics"]},
        "collector_state": evaluation["collector"]["state"],
        "freshness_state": evaluation["freshness"]["state"],
        "anomalies_count": evaluation["anomalies"]["active_count"],
    })

    transition_reason = (
        f"State transitioned from {from_state} to {current_health}. {evaluation['summary_reason']}"
    )

    record = HealthTransitionRecord(
        tenant_id=tenant_id,
        from_state=from_state,
        to_state=current_health,
        overall_health=current_health,
        reason=transition_reason,
        metrics_snapshot=metrics_snapshot,
        transitioned_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_health_history(
    db: Session,
    tenant_id: str,
    limit: int = 50,
) -> list[HealthTransitionRecord]:
    """Retrieves chronological health transition history for a tenant."""
    stmt = (
        select(HealthTransitionRecord)
        .where(HealthTransitionRecord.tenant_id == tenant_id)
        .order_by(desc(HealthTransitionRecord.transitioned_at))
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())
