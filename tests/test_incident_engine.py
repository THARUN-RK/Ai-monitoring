import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "central-platform"))

from app.database import Base, engine, SessionLocal
from app.models import IncidentRecord
from app.incidents import (
    IncidentPriority,
    IncidentStatus,
    determine_root_cause_and_action,
    calculate_incident_priority,
    correlate_anomalies_into_incidents,
    update_incident_status,
    get_tenant_incidents,
    get_incident_detail,
)
from app.main import list_incidents, get_incident, patch_incident_status, correlate_incidents_endpoint
from app.schemas import IncidentStatusUpdateIn

TEST_IDENTITY = {"tenant_id": "demo-tenant", "agent_id": "test-incident-agent"}


def setup_module():
    Base.metadata.create_all(bind=engine)


# -------------------------------------------------------------------------
# 1. Root Cause Analysis (RCA) Tests
# -------------------------------------------------------------------------

def test_rca_cpu_cascade_to_latency():
    now = datetime.now(timezone.utc)
    alerts = [
        {
            "alert_id": "ALT-1",
            "metric_name": "cpu_utilization",
            "service": "checkout",
            "current_value": 0.92,
            "severity": "critical",
            "timestamp": (now - timedelta(seconds=60)).isoformat(),
        },
        {
            "alert_id": "ALT-2",
            "metric_name": "http_latency_p95_ms",
            "service": "checkout",
            "current_value": 850.0,
            "severity": "warning",
            "timestamp": (now - timedelta(seconds=30)).isoformat(),
        },
        {
            "alert_id": "ALT-3",
            "metric_name": "http_error_rate",
            "service": "checkout",
            "current_value": 0.18,
            "severity": "critical",
            "timestamp": now.isoformat(),
        },
    ]

    rca, action, confidence = determine_root_cause_and_action(alerts)
    assert "CPU" in rca
    assert "saturation" in rca.lower() or "spiked" in rca.lower()
    assert "checkout" in rca
    assert confidence >= 0.90
    assert "horizontal replicas" in action.lower() or "slow database" in action.lower()


def test_rca_security_threat_detection():
    now = datetime.now(timezone.utc)
    alerts = [
        {
            "alert_id": "ALT-SEC-1",
            "metric_name": "failed_auth_attempts",
            "category": "security",
            "service": "api-gateway",
            "current_value": 8.0,
            "severity": "warning",
            "timestamp": now.isoformat(),
        }
    ]
    rca, action, confidence = determine_root_cause_and_action(alerts)
    assert "authentication" in rca.lower()
    assert "rate limit" in action.lower() or "captcha" in action.lower()


# -------------------------------------------------------------------------
# 2. Incident Prioritization Tests
# -------------------------------------------------------------------------

def test_incident_prioritization():
    # Critical with errors -> Critical
    p_crit = calculate_incident_priority([
        {"severity": "critical", "metric_name": "http_error_rate"},
        {"severity": "critical", "metric_name": "cpu_utilization"},
    ])
    assert p_crit == IncidentPriority.CRITICAL

    # Multiple warnings -> High
    p_high = calculate_incident_priority([
        {"severity": "warning", "metric_name": "cpu_utilization"},
        {"severity": "warning", "metric_name": "http_latency_p95_ms"},
        {"severity": "warning", "metric_name": "memory_utilization"},
    ])
    assert p_high == IncidentPriority.HIGH

    # Single warning -> Medium
    p_med = calculate_incident_priority([
        {"severity": "warning", "metric_name": "memory_utilization"},
    ])
    assert p_med == IncidentPriority.MEDIUM


# -------------------------------------------------------------------------
# 3. Incident Correlation & Grouping (3 Alerts -> 1 Incident)
# -------------------------------------------------------------------------

def test_group_related_alerts_into_single_incident():
    db = SessionLocal()
    tenant = "grouping-test-tenant"
    now = datetime.now(timezone.utc)

    try:
        # Clear previous test data
        db.query(IncidentRecord).filter(IncidentRecord.tenant_id == tenant).delete()
        db.commit()

        # Generate 3 related cascading alerts occurring in the same 5-minute window
        alerts = [
            {
                "alert_id": "ALT-101",
                "tenant_id": tenant,
                "service": "checkout",
                "metric_name": "cpu_utilization",
                "category": "infrastructure",
                "severity": "critical",
                "current_value": 0.94,
                "baseline_value": 0.45,
                "deviation_pct": 108.8,
                "timestamp": (now - timedelta(seconds=120)).isoformat(),
                "summary": "CPU utilization surged to 94.0%",
            },
            {
                "alert_id": "ALT-102",
                "tenant_id": tenant,
                "service": "checkout",
                "metric_name": "http_latency_p95_ms",
                "category": "infrastructure",
                "severity": "warning",
                "current_value": 780.0,
                "baseline_value": 180.0,
                "deviation_pct": 333.3,
                "timestamp": (now - timedelta(seconds=60)).isoformat(),
                "summary": "p95 Latency spiked to 780 ms",
            },
            {
                "alert_id": "ALT-103",
                "tenant_id": tenant,
                "service": "checkout",
                "metric_name": "http_error_rate",
                "category": "infrastructure",
                "severity": "critical",
                "current_value": 0.12,
                "baseline_value": 0.01,
                "deviation_pct": 1100.0,
                "timestamp": now.isoformat(),
                "summary": "HTTP Error rate elevated to 12.0%",
            },
        ]

        # Correlate alerts
        incidents = correlate_anomalies_into_incidents(db, tenant, alerts, time_window_seconds=300)

        # All 3 related alerts must be grouped into exactly ONE actionable incident!
        assert len(incidents) == 1, f"Expected 1 grouped incident, got {len(incidents)}"
        inc = incidents[0]
        assert inc.alert_count == 3
        assert inc.status == IncidentStatus.OPEN
        assert inc.priority == IncidentPriority.CRITICAL
        assert "CPU" in inc.probable_root_cause
        assert "checkout" in inc.affected_components
        assert inc.incident_id.startswith("INC-2026-")

    finally:
        db.close()


# -------------------------------------------------------------------------
# 4. Noise Reduction & Deduplication
# -------------------------------------------------------------------------

def test_noise_reduction_deduplicates_alerts():
    db = SessionLocal()
    tenant = "noise-reduction-tenant"
    now = datetime.now(timezone.utc)

    try:
        db.query(IncidentRecord).filter(IncidentRecord.tenant_id == tenant).delete()
        db.commit()

        initial_alert = [{
            "alert_id": "ALT-201",
            "tenant_id": tenant,
            "service": "checkout",
            "metric_name": "cpu_utilization",
            "category": "infrastructure",
            "severity": "critical",
            "current_value": 0.89,
            "baseline_value": 0.45,
            "deviation_pct": 97.7,
            "timestamp": now.isoformat(),
            "summary": "CPU utilization surged to 89.0%",
        }]

        # 1. First alert creates Incident
        inc1 = correlate_anomalies_into_incidents(db, tenant, initial_alert, time_window_seconds=300)
        assert len(inc1) == 1
        original_id = inc1[0].incident_id

        # 2. Subsequent alert for same component in active window attaches to existing incident
        cascading_alert = [{
            "alert_id": "ALT-202",
            "tenant_id": tenant,
            "service": "checkout",
            "metric_name": "http_latency_p95_ms",
            "category": "infrastructure",
            "severity": "warning",
            "current_value": 620.0,
            "baseline_value": 180.0,
            "deviation_pct": 244.4,
            "timestamp": (now + timedelta(seconds=15)).isoformat(),
            "summary": "p95 Latency elevated to 620 ms",
        }]

        inc2 = correlate_anomalies_into_incidents(db, tenant, cascading_alert, time_window_seconds=300)
        assert len(inc2) == 1
        # MUST retain the same incident ID (no new duplicate ticket spawned)
        assert inc2[0].incident_id == original_id
        assert inc2[0].alert_count == 2

        # Verify database total incident count for tenant is still 1
        all_incidents = get_tenant_incidents(db, tenant)
        assert len(all_incidents) == 1

    finally:
        db.close()


# -------------------------------------------------------------------------
# 5. Strict Tenant Isolation
# -------------------------------------------------------------------------

def test_tenant_isolation_prevents_cross_customer_correlation():
    db = SessionLocal()
    tenant_a = "tenant-alpha"
    tenant_b = "tenant-beta"
    now = datetime.now(timezone.utc)

    try:
        db.query(IncidentRecord).filter(IncidentRecord.tenant_id.in_([tenant_a, tenant_b])).delete()
        db.commit()

        # Alert for Tenant A
        alerts_a = [{
            "alert_id": "ALT-A",
            "tenant_id": tenant_a,
            "service": "checkout",
            "metric_name": "cpu_utilization",
            "category": "infrastructure",
            "severity": "critical",
            "current_value": 0.95,
            "baseline_value": 0.45,
            "deviation_pct": 111.0,
            "timestamp": now.isoformat(),
            "summary": "Tenant A CPU critical",
        }]

        # Alert for Tenant B
        alerts_b = [{
            "alert_id": "ALT-B",
            "tenant_id": tenant_b,
            "service": "checkout",
            "metric_name": "cpu_utilization",
            "category": "infrastructure",
            "severity": "critical",
            "current_value": 0.91,
            "baseline_value": 0.45,
            "deviation_pct": 102.0,
            "timestamp": now.isoformat(),
            "summary": "Tenant B CPU critical",
        }]

        inc_a = correlate_anomalies_into_incidents(db, tenant_a, alerts_a)
        inc_b = correlate_anomalies_into_incidents(db, tenant_b, alerts_b)

        assert inc_a[0].tenant_id == tenant_a
        assert inc_b[0].tenant_id == tenant_b
        assert inc_a[0].incident_id != inc_b[0].incident_id

        # Query Tenant A incidents: should NEVER return Tenant B's incident
        tenant_a_list = get_tenant_incidents(db, tenant_a)
        assert len(tenant_a_list) == 1
        assert tenant_a_list[0].tenant_id == tenant_a

    finally:
        db.close()


# -------------------------------------------------------------------------
# 6. Incident Lifecycle State Transitions
# -------------------------------------------------------------------------

def test_incident_lifecycle_transitions():
    db = SessionLocal()
    tenant = "lifecycle-tenant"
    now = datetime.now(timezone.utc)

    try:
        db.query(IncidentRecord).filter(IncidentRecord.tenant_id == tenant).delete()
        db.commit()

        inc = correlate_anomalies_into_incidents(db, tenant, [{
            "alert_id": "ALT-LIFE",
            "tenant_id": tenant,
            "service": "checkout",
            "metric_name": "memory_utilization",
            "category": "infrastructure",
            "severity": "warning",
            "current_value": 0.88,
            "baseline_value": 0.55,
            "deviation_pct": 60.0,
            "timestamp": now.isoformat(),
            "summary": "Memory drift alert",
        }])[0]

        # 1. Initial State: Open
        assert inc.status == IncidentStatus.OPEN
        assert inc.resolved_at is None

        # 2. Transition: Open -> Investigating
        up1 = update_incident_status(db, tenant, inc.incident_id, IncidentStatus.INVESTIGATING, note="SRE on-call assigned")
        assert up1.status == IncidentStatus.INVESTIGATING
        assert "SRE on-call assigned" in up1.recommended_investigation

        # 3. Transition: Investigating -> Resolved
        up2 = update_incident_status(db, tenant, inc.incident_id, IncidentStatus.RESOLVED, note="Restarted pod; memory recovered to 52%")
        assert up2.status == IncidentStatus.RESOLVED
        assert up2.resolved_at is not None

        # 4. Transition: Resolved -> Closed
        up3 = update_incident_status(db, tenant, inc.incident_id, IncidentStatus.CLOSED, note="Post-mortem verified")
        assert up3.status == IncidentStatus.CLOSED

    finally:
        db.close()


# -------------------------------------------------------------------------
# 7. FastAPI Incident Endpoints
# -------------------------------------------------------------------------

def test_api_incident_endpoints():
    db = SessionLocal()
    try:
        # 1. Trigger correlation via POST endpoint
        post_payload = {
            "alerts": [
                {
                    "alert_id": "ALT-API-1",
                    "tenant_id": "demo-tenant",
                    "service": "checkout",
                    "metric_name": "http_latency_p95_ms",
                    "category": "infrastructure",
                    "severity": "warning",
                    "current_value": 750.0,
                    "baseline_value": 180.0,
                    "deviation_pct": 316.6,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "summary": "Latency SLA breach",
                }
            ]
        }
        res_post = correlate_incidents_endpoint(post_payload, identity=TEST_IDENTITY, db=db)
        assert len(res_post) >= 1
        inc_id = res_post[0]["incident_id"]

        # 2. List incidents via GET endpoint
        res_list = list_incidents(identity=TEST_IDENTITY, db=db)
        assert isinstance(res_list, list)
        assert any(i["incident_id"] == inc_id for i in res_list)

        # 3. Get incident detail via GET endpoint
        detail = get_incident(incident_id=inc_id, identity=TEST_IDENTITY, db=db)
        assert detail["incident_id"] == inc_id
        assert "timeline" in detail
        assert len(detail["timeline"]) >= 1

        # 4. Update status via PATCH endpoint
        update_in = IncidentStatusUpdateIn(status="Investigating", note="Automation verified")
        updated = patch_incident_status(incident_id=inc_id, update=update_in, identity=TEST_IDENTITY, db=db)
        assert updated["status"] == "Investigating"

    finally:
        db.close()
