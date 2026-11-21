import sys
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import select

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "central-platform"))

from app.database import Base, engine, SessionLocal
from app.models import MetricRecord, AnomalyRecord
from app.aiops import (
    compute_rolling_stats,
    compute_z_score,
    compute_deviation_pct,
    compute_trend_slope,
    detect_cpu_anomaly,
    detect_memory_anomaly,
    detect_disk_anomaly,
    detect_network_anomaly,
    detect_security_anomaly,
    evaluate_aiops_telemetry,
)
from app.ml import score_feature_map, train_model
from app.main import anomaly_preview, aiops_insights, aiops_history

TEST_IDENTITY = {"tenant_id": "demo-tenant", "agent_id": "test-aiops-agent"}


def setup_module():
    Base.metadata.create_all(bind=engine)


# -------------------------------------------------------------------------
# 1. Statistical Engine & Baseline Tests
# -------------------------------------------------------------------------

def test_statistical_dynamic_baselines():
    # Normal distributed historical series
    history = [0.42, 0.44, 0.41, 0.43, 0.45, 0.42, 0.44, 0.43, 0.42, 0.44]
    stats = compute_rolling_stats(history)

    assert 0.40 <= stats["mean"] <= 0.45, "Mean should reflect nominal range"
    assert stats["std"] > 0, "Std should be non-zero"
    assert stats["upper"] > stats["mean"], "Upper dynamic threshold must exceed mean"

    # Test z-score
    z_norm = compute_z_score(0.43, stats["mean"], stats["std"])
    assert abs(z_norm) < 2.0, "Normal value must have |z| < 2.0"

    z_outlier = compute_z_score(0.92, stats["mean"], stats["std"])
    assert z_outlier > 3.0, "Extreme value must have z > 3.0"


# -------------------------------------------------------------------------
# 2. CPU Anomaly Detection Tests
# -------------------------------------------------------------------------

def test_cpu_normal_no_anomaly():
    history = [0.42, 0.44, 0.41, 0.43, 0.45, 0.42, 0.43]
    current = 0.44
    res = detect_cpu_anomaly(history, current)
    assert res is None, "Normal CPU should NOT trigger anomaly"


def test_cpu_spike_and_severity():
    history = [0.42, 0.43, 0.41, 0.44, 0.42]
    # Sudden jump from 0.42 to 0.88 (+46% spike)
    current = 0.88
    res = detect_cpu_anomaly(history, current)

    assert res is not None, "CPU spike MUST trigger anomaly"
    assert res["category"] == "cpu"
    assert res["severity"] == "critical"
    assert res["current_value"] == 0.88
    assert res["baseline_value"] > 0
    assert res["deviation_pct"] > 50.0
    assert res["confidence"] >= 0.70
    assert "Sudden CPU surge" in res["summary"]
    assert len(res["probable_cause"]) > 10
    assert len(res["recommended_action"]) > 10


# -------------------------------------------------------------------------
# 3. Memory Anomaly & Leak Detection Tests
# -------------------------------------------------------------------------

def test_memory_normal_no_anomaly():
    history = [0.55, 0.54, 0.56, 0.55, 0.55]
    res = detect_memory_anomaly(history, 0.55)
    assert res is None, "Normal memory should NOT trigger anomaly"


def test_memory_leak_growth_drift():
    # Monotonically increasing memory: 70% -> 85%
    history = [0.68, 0.71, 0.74, 0.77, 0.80, 0.82]
    current = 0.85
    res = detect_memory_anomaly(history, current)

    assert res is not None, "Progressive memory drift MUST trigger alert"
    assert res["category"] == "memory"
    assert res["severity"] in ("warning", "critical")
    assert "memory" in res["metric_name"]
    assert "allocation drift" in res["summary"] or "exceeds" in res["summary"]
    assert len(res["probable_cause"]) > 0
    assert len(res["recommended_action"]) > 0


# -------------------------------------------------------------------------
# 4. Disk Anomaly Detection Tests
# -------------------------------------------------------------------------

def test_disk_normal_and_critical():
    history = [0.42, 0.42, 0.42, 0.43]
    # Normal
    res_norm = detect_disk_anomaly(history, 0.43)
    assert res_norm is None

    # Critical disk fill-up
    res_crit = detect_disk_anomaly(history, 0.92)
    assert res_crit is not None
    assert res_crit["category"] == "disk"
    assert res_crit["severity"] == "critical"
    assert res_crit["current_value"] == 0.92
    assert "Storage volume pressure" in res_crit["summary"]


# -------------------------------------------------------------------------
# 5. Network Anomaly Detection Tests
# -------------------------------------------------------------------------

def test_network_latency_spike():
    lat_history = [150.0, 160.0, 155.0, 165.0, 158.0]
    err_history = [0.01, 0.01, 0.02, 0.01]

    # Normal network
    res_norm = detect_network_anomaly(lat_history, 162.0, err_history, 0.01)
    assert res_norm is None

    # Latency surge to 850ms with 18% error rate
    res_anom = detect_network_anomaly(lat_history, 850.0, err_history, 0.18)
    assert res_anom is not None
    assert res_anom["category"] == "network"
    assert res_anom["severity"] == "critical"
    assert res_anom["current_value"] == 850.0
    assert res_anom["deviation_pct"] > 100.0
    assert "latency at 850ms exceeds baseline" in res_anom["summary"]


# -------------------------------------------------------------------------
# 6. Security Anomaly Detection Tests
# -------------------------------------------------------------------------

def test_security_anomaly_and_privacy():
    # Normal login attempts
    res_norm = detect_security_anomaly(failed_attempts=1, rejected_fields_count=0)
    assert res_norm is None

    # Brute-force / repeated failed authentication attempts
    res_sec = detect_security_anomaly(failed_attempts=7, rejected_fields_count=3)
    assert res_sec is not None
    assert res_sec["category"] == "security"
    assert res_sec["severity"] == "critical"
    assert res_sec["confidence"] >= 0.85
    assert "Security threat alert: 7 repeated authentication challenges" in res_sec["summary"]

    # Verify no credentials or passwords in output
    serialized = str(res_sec)
    assert "password" not in serialized.lower() or "password" in res_sec["probable_cause"]
    assert "super_secret" not in serialized
    assert "sk-" not in serialized


# -------------------------------------------------------------------------
# 7. End-to-End Database & API Integration Tests
# -------------------------------------------------------------------------

def test_e2e_aiops_preview_endpoint():
    db = SessionLocal()
    try:
        # Seed baseline records into SQLite database
        now = datetime.now(timezone.utc)
        for i in range(25):
            db.add(MetricRecord(
                tenant_id="demo-tenant",
                agent_id="test-agent",
                batch_id=str(uuid.uuid4()),
                event_id=str(uuid.uuid4()),
                observed_at=now,
                service="checkout",
                environment="production",
                metric_name="cpu_utilization",
                metric_value=0.42 + (i % 3) * 0.02,
                unit="ratio",
                window_seconds=10,
                sample_count=1,
            ))
            db.add(MetricRecord(
                tenant_id="demo-tenant",
                agent_id="test-agent",
                batch_id=str(uuid.uuid4()),
                event_id=str(uuid.uuid4()),
                observed_at=now,
                service="checkout",
                environment="production",
                metric_name="memory_utilization",
                metric_value=0.54 + (i % 3) * 0.01,
                unit="ratio",
                window_seconds=10,
                sample_count=1,
            ))
            db.add(MetricRecord(
                tenant_id="demo-tenant",
                agent_id="test-agent",
                batch_id=str(uuid.uuid4()),
                event_id=str(uuid.uuid4()),
                observed_at=now,
                service="checkout",
                environment="production",
                metric_name="http_latency_p95_ms",
                metric_value=175.0 + (i % 4) * 5.0,
                unit="ms",
                window_seconds=10,
                sample_count=1,
            ))
            db.add(MetricRecord(
                tenant_id="demo-tenant",
                agent_id="test-agent",
                batch_id=str(uuid.uuid4()),
                event_id=str(uuid.uuid4()),
                observed_at=now,
                service="checkout",
                environment="production",
                metric_name="http_error_rate",
                metric_value=0.015,
                unit="ratio",
                window_seconds=10,
                sample_count=1,
            ))
        db.commit()

        # 1. Test nominal activity evaluation
        nominal_res = anomaly_preview(identity=TEST_IDENTITY, db=db)
        assert nominal_res["status"] == "scored"
        assert nominal_res["tenant_id"] == "demo-tenant"
        assert "dynamic_baselines" in nominal_res

        # 2. Test controlled test simulation mode (injecting CPU surge to 0.95)
        simulated_res = anomaly_preview(
            simulate_metric="cpu_utilization",
            simulate_value=0.95,
            identity=TEST_IDENTITY,
            db=db,
        )
        assert simulated_res["status"] == "scored"
        assert simulated_res["anomaly"] is True
        assert len(simulated_res["anomalies"]) > 0

        cpu_anom = next(a for a in simulated_res["anomalies"] if a["category"] == "cpu")
        assert cpu_anom["current_value"] == 0.95
        assert cpu_anom["severity"] == "critical"
        assert cpu_anom["deviation_pct"] > 100.0
        assert "Sudden CPU surge" in cpu_anom["summary"]
        assert len(cpu_anom["probable_cause"]) > 0
        assert len(cpu_anom["recommended_action"]) > 0

        # 3. Verify anomaly record was persisted in database
        persisted = db.scalars(
            select(AnomalyRecord).where(AnomalyRecord.tenant_id == "demo-tenant")
        ).all()
        assert len(persisted) > 0, "Anomaly should be persisted to AnomalyRecord table"

    finally:
        db.close()
