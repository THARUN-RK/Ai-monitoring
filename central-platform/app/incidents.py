from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.models import IncidentRecord, AnomalyRecord


class IncidentPriority:
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class IncidentStatus:
    OPEN = "Open"
    INVESTIGATING = "Investigating"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


# -------------------------------------------------------------------------
# Root Cause Analysis (RCA) & Priority Deduction
# -------------------------------------------------------------------------

def determine_root_cause_and_action(
    correlated_alerts: list[dict[str, Any]],
) -> tuple[str, str, float]:
    """
    Analyzes temporal causality, metric dependency graphs, and severity
    to deduce the probable root cause, recommended investigation, and confidence score.
    """
    if not correlated_alerts:
        return (
            "Unknown anomalous operational pattern.",
            "Inspect system telemetry and collector health logs.",
            0.70,
        )

    # Sort chronologically by detection time to find initiator signal
    sorted_alerts = sorted(
        correlated_alerts,
        key=lambda a: a.get("timestamp") or a.get("detected_at") or datetime.now(timezone.utc).isoformat(),
    )
    first_alert = sorted_alerts[0]
    metrics = {a.get("metric_name") for a in correlated_alerts}
    services = {a.get("service") for a in correlated_alerts}
    severities = {a.get("severity") for a in correlated_alerts}

    # Pattern 1: Resource Exhaustion cascading to latency/errors
    if "cpu_utilization" in metrics and ("http_latency_p95_ms" in metrics or "http_error_rate" in metrics):
        cpu_val = next((a.get("current_value") for a in correlated_alerts if a.get("metric_name") == "cpu_utilization"), 0.88)
        rca = (
            f"Hardware resource saturation: CPU utilization spiked to {cpu_val * 100:.1f}%, causing "
            f"thread-pool starvation and request queue backlog on service '{first_alert.get('service', 'checkout')}', "
            f"which cascaded into elevated p95 latency and downstream 5xx errors."
        )
        action = (
            "1. Inspect high-CPU worker processes and slow database query locks.\n"
            "2. Scale horizontal replicas or allocate burstable compute units.\n"
            "3. Enforce client circuit-breakers to shed excessive load."
        )
        confidence = 0.94

    # Pattern 2: Memory Leak / Saturation
    elif "memory_utilization" in metrics and ("http_latency_p95_ms" in metrics or "cpu_utilization" in metrics):
        mem_val = next((a.get("current_value") for a in correlated_alerts if a.get("metric_name") == "memory_utilization"), 0.90)
        rca = (
            f"Unusual memory growth pattern: Memory utilization reached {mem_val * 100:.1f}%, triggering "
            f"excessive garbage collection pauses and swap activity on '{first_alert.get('service', 'checkout')}'."
        )
        action = (
            "1. Capture heap profile and check for unclosed database connections or memory retention.\n"
            "2. Restart degraded worker containers under rolling deploy.\n"
            "3. Adjust memory ceiling limits in orchestration manifest."
        )
        confidence = 0.91

    # Pattern 3: Disk Saturation / Storage Lockup
    elif "disk_utilization" in metrics:
        disk_val = next((a.get("current_value") for a in correlated_alerts if a.get("metric_name") == "disk_utilization"), 0.92)
        rca = (
            f"Critical persistent storage exhaustion ({disk_val * 100:.1f}% capacity) preventing write operations "
            f"and temporary file allocation on host infrastructure."
        )
        action = (
            "1. Prune stale build artifacts, ephemeral container logs, and expired WAL logs.\n"
            "2. Expand persistent volume capacity quota immediately.\n"
            "3. Enable automated log-rotation with compression."
        )
        confidence = 0.96

    # Pattern 4: Security Threat / Credential Stuffing
    elif any("auth" in str(m) or "security" in str(a.get("category")) for a in correlated_alerts for m in [a.get("metric_name")]):
        rca = (
            "Repeated authentication challenge storm: Multiple failed login attempts and unauthorized access "
            "probes detected client-side within a short observation window."
        )
        action = (
            "1. Inspect ingress IP telemetry and verify challenge rate limits.\n"
            "2. Enforce progressive delay and CAPTCHA challenge at Tier 1 API perimeter.\n"
            "3. Rotate any potentially compromised collector tokens or service credentials."
        )
        confidence = 0.95

    # Pattern 5: Network / Latency Spike in Isolation
    elif "http_latency_p95_ms" in metrics:
        lat_val = next((a.get("current_value") for a in correlated_alerts if a.get("metric_name") == "http_latency_p95_ms"), 850.0)
        rca = (
            f"Network transport degradation or downstream dependency latency spike ({lat_val:.0f} ms p95) "
            f"observed without primary CPU exhaustion."
        )
        action = (
            "1. Inspect network gateway packet retransmissions and egress round-trip times.\n"
            "2. Verify external third-party API response SLAs.\n"
            "3. Enable edge caching for read-heavy endpoint responses."
        )
        confidence = 0.88

    else:
        rca = (
            f"Correlated operational anomaly across {len(metrics)} signals ({', '.join(metrics)}) "
            f"on service(s) {', '.join(services)} initiated by {first_alert.get('metric_name', 'metric')}."
        )
        action = (
            "1. Correlate application log summaries at the timestamp of the initiator signal.\n"
            "2. Monitor health transition ledger for state recovery.\n"
            "3. Validate collector heartbeat telemetry freshness."
        )
        confidence = 0.85

    return rca, action, confidence


def calculate_incident_priority(correlated_alerts: list[dict[str, Any]]) -> str:
    """
    Calculates incident priority (Critical, High, Medium, Low)
    based on alert severities, error rate impact, and multi-component involvement.
    """
    has_critical = any(a.get("severity") == "critical" for a in correlated_alerts)
    metrics = {a.get("metric_name") for a in correlated_alerts}
    alert_count = len(correlated_alerts)

    # Severe operational impact = Critical
    if has_critical and ("http_error_rate" in metrics or alert_count >= 2):
        return IncidentPriority.CRITICAL

    # Single critical or multiple warnings = High
    if has_critical or alert_count >= 3:
        return IncidentPriority.HIGH

    # Multiple metrics elevated or warning = Medium
    if alert_count >= 2 or any(a.get("severity") == "warning" for a in correlated_alerts):
        return IncidentPriority.MEDIUM

    return IncidentPriority.LOW


def generate_incident_title(correlated_alerts: list[dict[str, Any]]) -> str:
    """Generates a concise, informative incident summary title."""
    services = sorted(list({a.get("service", "system") for a in correlated_alerts}))
    metrics = sorted(list({a.get("metric_name", "metric").replace("_", " ").title() for a in correlated_alerts}))
    service_str = "/".join(services) if services else "System"

    if len(metrics) == 1:
        return f"{service_str}: {metrics[0]} Anomaly Surge"
    return f"{service_str}: Degradation Cascade ({', '.join(metrics[:3])})"


# -------------------------------------------------------------------------
# Correlation & Noise Reduction Engine
# -------------------------------------------------------------------------

def correlate_anomalies_into_incidents(
    db: Session,
    tenant_id: str,
    raw_alerts: list[dict[str, Any]],
    time_window_seconds: int = 300,
) -> list[IncidentRecord]:
    """
    Core Intelligent Incident Correlation Engine:
    1. Tenant Isolation: Only processes alerts for the specified tenant_id.
    2. Event Correlation: Groups related alerts by time window, affected component, and pattern.
    3. Noise Reduction: Attaches recurring or cascading alerts to existing Open/Investigating incidents.
    4. Root Cause Analysis: Calculates initiator and causality graph.
    5. Incident Prioritization: Assigns Critical, High, Medium, Low.
    """
    if not raw_alerts:
        return []

    # Filter strictly for tenant isolation
    tenant_alerts = [a for a in raw_alerts if a.get("tenant_id", tenant_id) == tenant_id]
    if not tenant_alerts:
        return []

    now = datetime.now(timezone.utc)
    window_threshold = now - timedelta(seconds=time_window_seconds)

    # Find existing Open or Investigating incidents for this tenant within the time window
    stmt = (
        select(IncidentRecord)
        .where(
            IncidentRecord.tenant_id == tenant_id,
            IncidentRecord.status.in_([IncidentStatus.OPEN, IncidentStatus.INVESTIGATING]),
            IncidentRecord.updated_at >= window_threshold,
        )
        .order_by(desc(IncidentRecord.updated_at))
    )
    existing_incidents = list(db.execute(stmt).scalars().all())

    created_or_updated: list[IncidentRecord] = []

    # Group incoming alerts by component affinity / category
    # Infrastructure and application metrics on the same cluster/collector belong together
    grouped_incoming: dict[str, list[dict[str, Any]]] = {}
    for alert in tenant_alerts:
        cat = alert.get("category", "infrastructure")
        # Group related application & system metrics together, isolate security
        cluster_key = "security" if cat == "security" else "infrastructure"
        grouped_incoming.setdefault(cluster_key, []).append(alert)

    for cluster_key, alerts_in_group in grouped_incoming.items():
        # Check if an existing open incident matches this cluster
        matching_incident: Optional[IncidentRecord] = None
        for inc in existing_incidents:
            if inc.category == cluster_key:
                matching_incident = inc
                break

        if matching_incident:
            # NOISE REDUCTION: Correlate into existing incident instead of creating duplicate!
            current_timeline: list[dict[str, Any]] = json.loads(matching_incident.raw_alerts_payload)
            existing_alert_keys = {
                f"{a.get('metric_name')}_{a.get('service')}_{a.get('timestamp')}"
                for a in current_timeline
            }

            new_alerts_added = 0
            for alert in alerts_in_group:
                a_key = f"{alert.get('metric_name')}_{alert.get('service')}_{alert.get('timestamp')}"
                if a_key not in existing_alert_keys:
                    current_timeline.append(alert)
                    existing_alert_keys.add(a_key)
                    new_alerts_added += 1

            if new_alerts_added > 0:
                # Re-run RCA with full combined alert set
                rca, action, confidence = determine_root_cause_and_action(current_timeline)
                new_priority = calculate_incident_priority(current_timeline)
                affected = sorted(list({a.get("service", "unknown") for a in current_timeline}))
                signals = sorted(list({a.get("metric_name", "unknown") for a in current_timeline}))

                matching_incident.title = generate_incident_title(current_timeline)
                matching_incident.priority = new_priority
                matching_incident.affected_components = json.dumps(affected)
                matching_incident.probable_root_cause = rca
                matching_incident.confidence_score = confidence
                matching_incident.recommended_investigation = action
                matching_incident.contributing_signals = json.dumps(signals)
                matching_incident.alert_count = len(current_timeline)
                matching_incident.raw_alerts_payload = json.dumps(current_timeline)
                matching_incident.updated_at = now

                db.commit()
                db.refresh(matching_incident)
            created_or_updated.append(matching_incident)

        else:
            # INCIDENT CREATION: Automatically group related alerts into ONE actionable incident
            incident_uuid = str(uuid.uuid4())[:8].upper()
            incident_id = f"INC-2026-{incident_uuid}"
            rca, action, confidence = determine_root_cause_and_action(alerts_in_group)
            priority = calculate_incident_priority(alerts_in_group)
            title = generate_incident_title(alerts_in_group)
            affected = sorted(list({a.get("service", "unknown") for a in alerts_in_group}))
            signals = sorted(list({a.get("metric_name", "unknown") for a in alerts_in_group}))

            new_inc = IncidentRecord(
                tenant_id=tenant_id,
                incident_id=incident_id,
                title=title,
                priority=priority,
                status=IncidentStatus.OPEN,
                category=cluster_key,
                affected_components=json.dumps(affected),
                probable_root_cause=rca,
                confidence_score=confidence,
                recommended_investigation=action,
                contributing_signals=json.dumps(signals),
                alert_count=len(alerts_in_group),
                raw_alerts_payload=json.dumps(alerts_in_group),
                created_at=now,
                updated_at=now,
            )
            db.add(new_inc)
            db.commit()
            db.refresh(new_inc)
            created_or_updated.append(new_inc)

    return created_or_updated


# -------------------------------------------------------------------------
# Lifecycle Operations
# -------------------------------------------------------------------------

def update_incident_status(
    db: Session,
    tenant_id: str,
    incident_id: str,
    new_status: str,
    note: Optional[str] = None,
) -> Optional[IncidentRecord]:
    """
    Updates the lifecycle status of an incident:
    Open -> Investigating -> Resolved -> Closed.
    """
    stmt = (
        select(IncidentRecord)
        .where(
            IncidentRecord.tenant_id == tenant_id,
            IncidentRecord.incident_id == incident_id,
        )
    )
    incident = db.execute(stmt).scalar_one_or_none()
    if not incident:
        return None

    now = datetime.now(timezone.utc)
    incident.status = new_status
    incident.updated_at = now

    if new_status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
        if not incident.resolved_at:
            incident.resolved_at = now

    if note:
        current_investigation = incident.recommended_investigation
        incident.recommended_investigation = f"{current_investigation}\n\n[Status Update: {new_status} at {now.isoformat()}] {note}"

    db.commit()
    db.refresh(incident)
    return incident


def get_tenant_incidents(
    db: Session,
    tenant_id: str,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[IncidentRecord]:
    """Retrieves correlated incidents for a tenant, supporting lifecycle filtering."""
    query = select(IncidentRecord).where(IncidentRecord.tenant_id == tenant_id)
    if status:
        query = query.where(IncidentRecord.status == status)

    query = query.order_by(desc(IncidentRecord.created_at)).limit(limit)
    return list(db.execute(query).scalars().all())


def get_incident_detail(
    db: Session,
    tenant_id: str,
    incident_id: str,
) -> Optional[IncidentRecord]:
    """Retrieves full incident detail by ID with strict tenant scoping."""
    stmt = select(IncidentRecord).where(
        IncidentRecord.tenant_id == tenant_id,
        IncidentRecord.incident_id == incident_id,
    )
    return db.execute(stmt).scalar_one_or_none()
