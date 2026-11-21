import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy import select

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "central-platform"))

from app.database import Base, engine, SessionLocal
from app.models import MetricRecord, CollectorRecord, HealthTransitionRecord
from app.health import (
    HealthState,
    HealthConfig,
    MetricThresholdConfig,
    worst_state,
    evaluate_single_metric,
    evaluate_collector_availability,
    evaluate_telemetry_freshness,
    evaluate_aiops_anomalies,
    evaluate_system_health,
    record_transition_if_changed,
    get_health_history,
)
from app.main import get_system_health, get_health_transition_history, evaluate_custom_health

TEST_IDENTITY = {"tenant_id": "demo-tenant", "agent_id": "test-sre-agent"}


def setup_module():
    Base.metadata.create_all(bind=engine)


# -------------------------------------------------------------------------
# 1. State Severity & Four-State Worst Case Ranking
# -------------------------------------------------------------------------

def test_four_state_worst_case_ranking():
    assert worst_state(HealthState.EXCELLENT, HealthState.GOOD) == HealthState.GOOD
    assert worst_state(HealthState.EXCELLENT, HealthState.FAIR) == HealthState.FAIR
    assert worst_state(HealthState.GOOD, HealthState.FAIR, HealthState.POOR) == HealthState.POOR
    assert worst_state(HealthState.EXCELLENT, HealthState.EXCELLENT) == HealthState.EXCELLENT


# -------------------------------------------------------------------------
# 2. Metric Evaluation Under Configurable Thresholds
# -------------------------------------------------------------------------

def test_metric_normal_cpu_ram_excellent():
    config = HealthConfig()
    cpu_res = evaluate_single_metric("cpu_utilization", 0.42, "ratio", config)
    assert cpu_res["state"] == HealthState.EXCELLENT
    assert "optimal" in cpu_res["reason"].lower()

    ram_res = evaluate_single_metric("memory_utilization", 0.50, "ratio", config)
    assert ram_res["state"] == HealthState.EXCELLENT


def test_metric_minor_deviation_good():
    config = HealthConfig()
    # 0.68 is between excellent_max (0.60) and good_max (0.75)
    cpu_res = evaluate_single_metric("cpu_utilization", 0.68, "ratio", config)
    assert cpu_res["state"] == HealthState.GOOD
    assert "nominal" in cpu_res["reason"].lower()


def test_metric_elevated_resource_fair():
    config = HealthConfig()
    # 0.82 is between good_max (0.75) and fair_max (0.88)
    cpu_res = evaluate_single_metric("cpu_utilization", 0.82, "ratio", config)
    assert cpu_res["state"] == HealthState.FAIR
    assert "elevated" in cpu_res["reason"].lower()
    assert "requires attention" in cpu_res["reason"].lower()


def test_metric_severe_degradation_poor():
    config = HealthConfig()
    # 0.94 is >= fair_max (0.88)
    cpu_res = evaluate_single_metric("cpu_utilization", 0.94, "ratio", config)
    assert cpu_res["state"] == HealthState.POOR
    assert "critical degradation" in cpu_res["reason"].lower()


def test_custom_configurable_thresholds():
    # Strict custom thresholds where 0.50 is already FAIR
    custom_cfg = HealthConfig(
        cpu_utilization=MetricThresholdConfig(excellent_max=0.30, good_max=0.45, fair_max=0.70)
    )
    res = evaluate_single_metric("cpu_utilization", 0.50, "ratio", custom_cfg)
    assert res["state"] == HealthState.FAIR
    assert res["threshold_applied"]["good_max"] == 0.45


# -------------------------------------------------------------------------
# 3. Collector Availability Tests
# -------------------------------------------------------------------------

def test_collector_online_and_fresh():
    config = HealthConfig()
    now = datetime.now(timezone.utc)
    collector = {
        "collector_id": "collector-1",
        "status": "online",
        "last_heartbeat": (now - timedelta(seconds=5)).isoformat(),
    }
    col_res = evaluate_collector_availability(collector, now, config)
    assert col_res["state"] == HealthState.EXCELLENT
    assert "active" in col_res["reason"].lower()


def test_collector_delayed_heartbeat_fair():
    config = HealthConfig()
    now = datetime.now(timezone.utc)
    # 35 seconds ago -> warning threshold is 30s
    collector = {
        "collector_id": "collector-1",
        "status": "online",
        "last_heartbeat": (now - timedelta(seconds=35)).isoformat(),
    }
    col_res = evaluate_collector_availability(collector, now, config)
    assert col_res["state"] == HealthState.FAIR
    assert "delayed" in col_res["reason"].lower()


def test_collector_offline_poor():
    config = HealthConfig()
    now = datetime.now(timezone.utc)
    # Collector status explicitly offline
    collector = {
        "collector_id": "collector-1",
        "status": "offline",
        "last_heartbeat": (now - timedelta(seconds=5)).isoformat(),
    }
    col_res = evaluate_collector_availability(collector, now, config)
    assert col_res["state"] == HealthState.POOR
    assert "offline" in col_res["reason"].lower()

    # Collector heartbeat missing for > 60s
    collector_stale = {
        "collector_id": "collector-1",
        "status": "online",
        "last_heartbeat": (now - timedelta(seconds=75)).isoformat(),
    }
    col_res2 = evaluate_collector_availability(collector_stale, now, config)
    assert col_res2["state"] == HealthState.POOR
    assert "missing" in col_res2["reason"].lower()


# -------------------------------------------------------------------------
# 4. Telemetry Freshness & Staleness Downgrade Tests
# -------------------------------------------------------------------------

def test_telemetry_freshness_levels():
    config = HealthConfig()
    now = datetime.now(timezone.utc)

    # 1. Fresh (< 15s) -> EXCELLENT
    f_exc = evaluate_telemetry_freshness(now - timedelta(seconds=8), now, config)
    assert f_exc["state"] == HealthState.EXCELLENT

    # 2. Active (15s - 30s) -> GOOD
    f_good = evaluate_telemetry_freshness(now - timedelta(seconds=22), now, config)
    assert f_good["state"] == HealthState.GOOD

    # 3. Stale (30s - 60s) -> FAIR (Downgraded due to delayed telemetry)
    f_fair = evaluate_telemetry_freshness(now - timedelta(seconds=45), now, config)
    assert f_fair["state"] == HealthState.FAIR
    assert "stale" in f_fair["reason"].lower()
    assert "downgraded" in f_fair["reason"].lower()

    # 4. Expired (>= 60s) -> POOR (Critical missing telemetry)
    f_poor = evaluate_telemetry_freshness(now - timedelta(seconds=90), now, config)
    assert f_poor["state"] == HealthState.POOR
    assert "expired or missing" in f_poor["reason"].lower()

    # 5. Missing altogether (None) -> POOR
    f_none = evaluate_telemetry_freshness(None, now, config)
    assert f_none["state"] == HealthState.POOR
    assert "missing" in f_none["reason"].lower()


# -------------------------------------------------------------------------
# 5. AIOps Anomaly Health Evaluation
# -------------------------------------------------------------------------

def test_aiops_anomaly_health_impact():
    # No anomalies -> EXCELLENT
    res_none = evaluate_aiops_anomalies([])
    assert res_none["state"] == HealthState.EXCELLENT

    # Warning anomaly -> FAIR
    res_warn = evaluate_aiops_anomalies([{"severity": "warning", "metric_name": "http_latency_p95_ms"}])
    assert res_warn["state"] == HealthState.FAIR

    # Critical anomaly -> POOR
    res_crit = evaluate_aiops_anomalies([
        {"severity": "warning", "metric_name": "http_latency_p95_ms"},
        {"severity": "critical", "metric_name": "cpu_utilization"},
    ])
    assert res_crit["state"] == HealthState.POOR
    assert res_crit["critical_count"] == 1


# -------------------------------------------------------------------------
# 6. Overall System Health Evaluation & Explainability
# -------------------------------------------------------------------------

def test_evaluate_system_health_composite_excellent():
    now = datetime.now(timezone.utc)
    metrics = {
        "cpu_utilization": (0.35, "ratio"),
        "memory_utilization": (0.45, "ratio"),
        "disk_utilization": (0.40, "ratio"),
        "http_latency_p95_ms": (150.0, "ms"),
        "http_error_rate": (0.005, "ratio"),
    }
    collector = {"collector_id": "c1", "status": "online", "last_heartbeat": (now - timedelta(seconds=5)).isoformat()}
    last_telemetry = now - timedelta(seconds=5)

    res = evaluate_system_health(
        tenant_id="test-tenant",
        metrics_map=metrics,
        collector=collector,
        last_telemetry_at=last_telemetry,
        active_anomalies=[],
        now=now,
    )

    assert res["overall_health"] == HealthState.EXCELLENT
    assert "EXCELLENT" in res["summary_reason"]


def test_evaluate_system_health_staleness_downgrade():
    now = datetime.now(timezone.utc)
    metrics = {
        "cpu_utilization": (0.35, "ratio"),
        "memory_utilization": (0.45, "ratio"),
    }
    collector = {"collector_id": "c1", "status": "online", "last_heartbeat": (now - timedelta(seconds=5)).isoformat()}
    # Stale telemetry: 45s ago
    last_telemetry = now - timedelta(seconds=45)

    res = evaluate_system_health(
        tenant_id="test-tenant",
        metrics_map=metrics,
        collector=collector,
        last_telemetry_at=last_telemetry,
        active_anomalies=[],
        now=now,
    )

    # Even though CPU/RAM are optimal, stale telemetry downgrades overall to FAIR
    assert res["overall_health"] == HealthState.FAIR
    assert "stale" in res["summary_reason"].lower()


# -------------------------------------------------------------------------
# 7. State Transition Recording & Persistence
# -------------------------------------------------------------------------

def test_state_transition_recording():
    db = SessionLocal()
    tenant = "transition-test-tenant"
    now = datetime.now(timezone.utc)

    try:
        # Clear previous test transitions
        db.query(HealthTransitionRecord).filter(HealthTransitionRecord.tenant_id == tenant).delete()
        db.commit()

        # 1. First evaluation: EXCELLENT
        eval_exc = evaluate_system_health(
            tenant_id=tenant,
            metrics_map={"cpu_utilization": (0.30, "ratio")},
            collector={"collector_id": "c1", "status": "online", "last_heartbeat": now.isoformat()},
            last_telemetry_at=now,
            now=now,
        )
        rec1 = record_transition_if_changed(db, tenant, eval_exc)
        assert rec1 is not None
        assert rec1.from_state == "INITIAL"
        assert rec1.to_state == HealthState.EXCELLENT
        assert rec1.transitioned_at is not None

        # 2. Identical evaluation should NOT duplicate transition record
        rec2 = record_transition_if_changed(db, tenant, eval_exc)
        assert rec2 is None, "Should not record duplicate transition when state has not changed"

        # 3. Transition to FAIR due to elevated CPU
        eval_fair = evaluate_system_health(
            tenant_id=tenant,
            metrics_map={"cpu_utilization": (0.82, "ratio")},
            collector={"collector_id": "c1", "status": "online", "last_heartbeat": now.isoformat()},
            last_telemetry_at=now,
            now=now,
        )
        rec3 = record_transition_if_changed(db, tenant, eval_fair)
        assert rec3 is not None
        assert rec3.from_state == HealthState.EXCELLENT
        assert rec3.to_state == HealthState.FAIR
        assert "elevated" in rec3.reason.lower()

        # 4. Transition to POOR due to collector offline
        eval_poor = evaluate_system_health(
            tenant_id=tenant,
            metrics_map={"cpu_utilization": (0.82, "ratio")},
            collector={"collector_id": "c1", "status": "offline", "last_heartbeat": now.isoformat()},
            last_telemetry_at=now,
            now=now,
        )
        rec4 = record_transition_if_changed(db, tenant, eval_poor)
        assert rec4 is not None
        assert rec4.from_state == HealthState.FAIR
        assert rec4.to_state == HealthState.POOR
        assert "offline" in rec4.reason.lower()

        # Verify history query
        history = get_health_history(db, tenant)
        assert len(history) == 3
        # Chronological descending order: POOR -> FAIR -> EXCELLENT
        assert history[0].to_state == HealthState.POOR
        assert history[1].to_state == HealthState.FAIR
        assert history[2].to_state == HealthState.EXCELLENT

    finally:
        db.close()


# -------------------------------------------------------------------------
# 8. API Endpoints Integration Tests
# -------------------------------------------------------------------------

def test_api_health_system_and_history_endpoints():
    db = SessionLocal()
    try:
        # Test GET /api/v1/health/system
        res = get_system_health(force_record=True, identity=TEST_IDENTITY, db=db)
        assert "overall_health" in res
        assert res["overall_health"] in [HealthState.EXCELLENT, HealthState.GOOD, HealthState.FAIR, HealthState.POOR]
        assert "metrics" in res
        assert "collector" in res
        assert "freshness" in res
        assert "anomalies" in res
        assert "latest_transition" in res

        # Test GET /api/v1/health/history
        history_res = get_health_transition_history(limit=10, identity=TEST_IDENTITY, db=db)
        assert isinstance(history_res, list)
        assert len(history_res) >= 1
        assert "from_state" in history_res[0]
        assert "to_state" in history_res[0]
        assert "transitioned_at" in history_res[0]

        # Test POST /api/v1/health/evaluate with custom simulation
        custom_sim = {
            "cpu": 0.95,
            "memory": 0.95,
            "record_transition": True,
        }
        eval_custom = evaluate_custom_health(custom_sim, identity=TEST_IDENTITY, db=db)
        assert eval_custom["overall_health"] == HealthState.POOR
        assert any("cpu" in r.lower() for r in eval_custom["reasons"])
    finally:
        db.close()
