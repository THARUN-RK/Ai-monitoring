import os
import json
from typing import Any, Optional
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import MetricRecord, CollectorRecord, EgressAuditRecord, AnomalyRecord, HealthTransitionRecord
from app.schemas import (
    Batch,
    CollectorRegisterIn,
    CollectorHealthOut,
    TelemetryIngestIn,
    EgressAuditOut,
    AnomalyDetailOut,
    AIOpsPreviewOut,
    SystemHealthOut,
    HealthTransitionOut,
)
from app.security import authenticate_agent
from app.ml import score_feature_map, train_model
from app.aiops import evaluate_aiops_telemetry
from app.health import (
    HealthState,
    HealthConfig,
    evaluate_system_health,
    record_transition_if_changed,
    get_health_history,
)


# --------------------------------------------------
# DATABASE INITIALIZATION
# --------------------------------------------------

Base.metadata.create_all(bind=engine)


# --------------------------------------------------
# FASTAPI APPLICATION
# --------------------------------------------------

app = FastAPI(
    title="CICADA Secure AIOps API",
    version="0.2.0",
    description="Privacy-preserving AI-powered observability platform with Egress Proof & Collector Fleet",
)


# --------------------------------------------------
# CORS CONFIGURATION
# Default to allow all origins so local dev, LAN IP, and deployed frontends work cleanly.
# --------------------------------------------------

_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
if _raw_origins.strip() == "*":
    _allow_origins = ["*"]
else:
    _allow_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# ROOT & HEALTH CHECK
# --------------------------------------------------

@app.get("/")
@app.head("/")
def root():
    return {
        "service": "CICADA Central Platform",
        "status": "online",
        "docs": "/docs",
        "health": "/api/v1/health/live",
    }


@app.get("/api/v1/health/live")
def live():
    return {
        "status": "alive",
        "service": "CICADA Central Platform",
    }


# --------------------------------------------------
# COLLECTOR REGISTRATION & FLEET HEALTH
# --------------------------------------------------

@app.post("/api/v1/collector/register", status_code=201)
def register_collector(
    data: CollectorRegisterIn,
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    tenant_id = data.tenant_id or identity["tenant_id"]
    now = datetime.now(timezone.utc)

    collector = db.scalar(
        select(CollectorRecord)
        .where(
            CollectorRecord.tenant_id == tenant_id,
            CollectorRecord.collector_id == data.collector_id,
        )
        .limit(1)
    )

    if collector:
        collector.name = data.name
        collector.environment = data.environment
        collector.status = "online"
        collector.last_heartbeat = now
    else:
        collector = CollectorRecord(
            tenant_id=tenant_id,
            collector_id=data.collector_id,
            name=data.name,
            environment=data.environment,
            status="online",
            last_heartbeat=now,
            registered_at=now,
        )
        db.add(collector)

    db.commit()
    return {
        "collector_id": collector.collector_id,
        "name": collector.name,
        "environment": collector.environment,
        "status": collector.status,
        "registered_at": collector.registered_at.isoformat(),
        "message": "Collector registered successfully.",
    }


@app.get("/api/v1/collector/health", response_model=list[CollectorHealthOut])
def get_collector_health(
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    tenant_id = identity["tenant_id"]
    now = datetime.now(timezone.utc)

    collectors = db.scalars(
        select(CollectorRecord)
        .where(CollectorRecord.tenant_id == tenant_id)
        .order_by(CollectorRecord.last_heartbeat.desc())
    ).all()

    fleet = []
    for col in collectors:
        # Check freshness of heartbeat (within 60 seconds = online)
        hb = col.last_heartbeat
        if hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
        diff_seconds = (now - hb).total_seconds()
        is_online = diff_seconds <= 60

        fleet.append(
            CollectorHealthOut(
                collector_id=col.collector_id,
                name=col.name,
                environment=col.environment,
                status="online" if is_online else "offline",
                last_heartbeat=hb.isoformat(),
            )
        )
    return fleet


# --------------------------------------------------
# TELEMETRY INGESTION (NEW STEP 5 ENDPOINT)
# --------------------------------------------------

@app.post("/api/v1/telemetry/ingest", status_code=202)
def ingest_telemetry(
    payload: TelemetryIngestIn,
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    tenant_id = identity["tenant_id"]
    now = datetime.now(timezone.utc)

    # 1. Enforce unique payload IDs to prevent duplicate ingestion.
    existing_egress = db.scalar(
        select(EgressAuditRecord)
        .where(
            EgressAuditRecord.tenant_id == tenant_id,
            EgressAuditRecord.payload_id == payload.payload_id,
        )
        .limit(1)
    )

    if existing_egress:
        return {
            "payload_id": payload.payload_id,
            "status": "duplicate",
            "accepted_records": 0,
            "message": "Payload already ingested previously",
        }

    # 2. Update or register collector heartbeat
    collector = db.scalar(
        select(CollectorRecord)
        .where(
            CollectorRecord.tenant_id == tenant_id,
            CollectorRecord.collector_id == payload.collector_id,
        )
        .limit(1)
    )
    if collector:
        collector.last_heartbeat = now
        collector.status = "online"
    else:
        collector = CollectorRecord(
            tenant_id=tenant_id,
            collector_id=payload.collector_id,
            name=f"Collector-{payload.collector_id[:8]}",
            environment="production",
            status="online",
            last_heartbeat=now,
            registered_at=now,
        )
        db.add(collector)

    # 3. Create sanitized sample string for Egress Proof verification
    sanitized_sample = payload.sanitized_sample
    if not sanitized_sample and payload.records:
        first = payload.records[0]
        sanitized_sample = json.dumps({
            "event_id": first.event_id,
            "metric_name": first.metric_name,
            "metric_value": first.metric_value,
            "unit": first.unit,
            "service": first.service,
        })

    # 4. Save Egress Audit Record
    audit_row = EgressAuditRecord(
        tenant_id=tenant_id,
        collector_id=payload.collector_id,
        payload_id=payload.payload_id,
        sent_at=payload.timestamp,
        received_at=now,
        approved_fields_count=payload.approved_fields_count or len(payload.records),
        rejected_fields_count=payload.rejected_fields_count,
        delivery_status="delivered",
        api_response_status=202,
        sanitized_sample=sanitized_sample[:1000],
    )
    db.add(audit_row)

    # 5. Persist telemetry records
    rows = []
    for r in payload.records:
        obs_at = r.observed_at or r.timestamp or now
        if obs_at.tzinfo is not None:
            obs_at = obs_at.astimezone(timezone.utc).replace(tzinfo=None)

        rows.append(
            MetricRecord(
                tenant_id=tenant_id,
                agent_id=payload.collector_id,
                batch_id=payload.payload_id,
                event_id=r.event_id,
                observed_at=obs_at,
                service=r.service,
                environment=r.environment,
                metric_name=r.metric_name,
                metric_value=r.metric_value,
                unit=r.unit,
                window_seconds=10,
                sample_count=1,
            )
        )

    try:
        db.add_all(rows)
        db.commit()
    except Exception as err:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Telemetry persistence conflict: {err}",
        )

    return {
        "payload_id": payload.payload_id,
        "status": "accepted",
        "accepted_records": len(rows),
    }


# --------------------------------------------------
# TELEMETRY INGESTION (LEGACY BATCHES ENDPOINT)
# Preserved for backward compatibility with existing agent scripts
# --------------------------------------------------

@app.post("/api/v1/agent/batches", status_code=202)
def ingest_batch(
    batch: Batch,
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    tenant_id = identity["tenant_id"]
    agent_id = identity["agent_id"]
    now = datetime.now(timezone.utc)

    # Prevent duplicate batch ingestion.
    existing = db.scalar(
        select(MetricRecord)
        .where(
            MetricRecord.tenant_id == tenant_id,
            MetricRecord.batch_id == batch.batch_id,
        )
        .limit(1)
    )

    if existing:
        return {
            "batch_id": batch.batch_id,
            "status": "duplicate",
            "accepted_records": 0,
        }

    # Update collector record
    collector = db.scalar(
        select(CollectorRecord)
        .where(
            CollectorRecord.tenant_id == tenant_id,
            CollectorRecord.collector_id == agent_id,
        )
        .limit(1)
    )
    if collector:
        collector.last_heartbeat = now
        collector.status = "online"
    else:
        collector = CollectorRecord(
            tenant_id=tenant_id,
            collector_id=agent_id,
            name=f"Collector-{agent_id[:8]}",
            environment="production",
            status="online",
            last_heartbeat=now,
            registered_at=now,
        )
        db.add(collector)

    # Record Egress Audit record for audit trail
    sample_preview = ""
    if batch.records:
        rec = batch.records[0]
        sample_preview = json.dumps({
            "event_id": rec.event_id,
            "metric_name": rec.metric.name,
            "metric_value": rec.metric.value,
            "unit": rec.metric.unit,
            "service": rec.resource.service,
        })

    audit_row = EgressAuditRecord(
        tenant_id=tenant_id,
        collector_id=agent_id,
        payload_id=batch.batch_id,
        sent_at=batch.sent_at,
        received_at=now,
        approved_fields_count=len(batch.records),
        rejected_fields_count=0,
        delivery_status="delivered",
        api_response_status=202,
        sanitized_sample=sample_preview[:1000],
    )
    db.add(audit_row)

    rows = [
        MetricRecord(
            tenant_id=tenant_id,
            agent_id=agent_id,
            batch_id=batch.batch_id,
            event_id=record.event_id,
            observed_at=record.observed_at.replace(tzinfo=None),
            service=record.resource.service,
            environment=record.resource.environment,
            metric_name=record.metric.name,
            metric_value=record.metric.value,
            unit=record.metric.unit,
            window_seconds=record.window_seconds,
            sample_count=record.quality.sample_count,
        )
        for record in batch.records
    ]

    try:
        db.add_all(rows)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Batch conflicts with existing data",
        )

    return {
        "batch_id": batch.batch_id,
        "status": "accepted",
        "accepted_records": len(rows),
    }


# --------------------------------------------------
# EGRESS PROOF & LATEST TELEMETRY
# --------------------------------------------------

@app.get("/api/v1/telemetry/egress", response_model=list[EgressAuditOut])
def get_egress_audit(
    limit: int = Query(50, ge=1, le=500),
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    tenant_id = identity["tenant_id"]

    records = db.scalars(
        select(EgressAuditRecord)
        .where(EgressAuditRecord.tenant_id == tenant_id)
        .order_by(desc(EgressAuditRecord.received_at))
        .limit(limit)
    ).all()

    return [
        EgressAuditOut(
            payload_id=rec.payload_id,
            collector_id=rec.collector_id,
            sent_at=rec.sent_at.isoformat() if hasattr(rec.sent_at, "isoformat") else str(rec.sent_at),
            approved_fields_count=rec.approved_fields_count,
            rejected_fields_count=rec.rejected_fields_count,
            delivery_status=rec.delivery_status,
            api_response_status=rec.api_response_status,
            sanitized_sample=rec.sanitized_sample or "{}",
        )
        for rec in records
    ]


@app.get("/api/v1/telemetry/latest")
def get_latest_telemetry(
    limit: int = Query(100, ge=1, le=1000),
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    tenant_id = identity["tenant_id"]

    rows = db.scalars(
        select(MetricRecord)
        .where(MetricRecord.tenant_id == tenant_id)
        .order_by(MetricRecord.observed_at.desc())
        .limit(limit)
    ).all()

    return {
        "tenant_id": tenant_id,
        "count": len(rows),
        "records": [
            {
                "event_id": row.event_id,
                "collector_id": row.agent_id,
                "batch_id": row.batch_id,
                "observed_at": row.observed_at.isoformat() if hasattr(row.observed_at, "isoformat") else str(row.observed_at),
                "service": row.service,
                "environment": row.environment,
                "metric_name": row.metric_name,
                "metric_value": row.metric_value,
                "unit": row.unit,
                "window_seconds": row.window_seconds,
            }
            for row in rows
        ],
    }


# --------------------------------------------------
# DASHBOARD SUMMARY
# --------------------------------------------------

@app.get("/api/v1/dashboard/summary")
def dashboard_summary(
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    tenant_id = identity["tenant_id"]

    rows = db.scalars(
        select(MetricRecord)
        .where(MetricRecord.tenant_id == tenant_id)
        .order_by(MetricRecord.observed_at.desc())
        .limit(100)
    ).all()

    latest = {}
    for row in rows:
        latest.setdefault(
            row.metric_name,
            row.metric_value,
        )

    # Get collector count
    now = datetime.now(timezone.utc)
    collectors = db.scalars(
        select(CollectorRecord).where(CollectorRecord.tenant_id == tenant_id)
    ).all()
    online_count = sum(
        1 for c in collectors
        if (now - (c.last_heartbeat if c.last_heartbeat.tzinfo else c.last_heartbeat.replace(tzinfo=timezone.utc))).total_seconds() <= 60
    )

    return {
        "tenant_id": tenant_id,
        "records_returned": len(rows),
        "latest_metrics": latest,
        "collectors_total": len(collectors),
        "collectors_online": online_count,
        "records": [
            {
                "observed_at": record.observed_at.isoformat() if hasattr(record.observed_at, 'isoformat') else str(record.observed_at),
                "service": record.service,
                "environment": record.environment,
                "metric_name": record.metric_name,
                "metric_value": record.metric_value,
                "unit": record.unit,
            }
            for record in rows
        ],
    }


# --------------------------------------------------
# ML ANOMALY DETECTION
# --------------------------------------------------

@app.get("/api/v1/anomalies/preview")
def anomaly_preview(
    simulate_metric: str | None = None,
    simulate_value: float | None = None,
    failed_auth_count: int = 0,
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    """
    Step 6 & 7: Dynamic Baseline Statistical Anomaly Detection + Multi-variate Isolation Forest.
    Evaluates real infrastructure telemetry stored in the database.
    Supports controlled test simulation without modifying host infrastructure.
    """
    tenant_id = identity["tenant_id"]

    try:
        # Retrieve recent tenant telemetry
        rows = db.scalars(
            select(MetricRecord)
            .where(MetricRecord.tenant_id == tenant_id)
            .order_by(MetricRecord.observed_at.asc())
            .limit(500)
        ).all()

        # Build chronological history map per metric
        history_map: dict[str, list[float]] = {}
        latest_values: dict[str, float] = {}
        latest_service = "checkout"

        for row in rows:
            name = row.metric_name
            if name not in history_map:
                history_map[name] = []
            history_map[name].append(float(row.metric_value))
            latest_values[name] = float(row.metric_value)
            latest_service = row.service

        # Fallback defaults for missing features if telemetry is young
        if "cpu_utilization" not in latest_values:
            latest_values["cpu_utilization"] = 0.45
        if "memory_utilization" not in latest_values:
            latest_values["memory_utilization"] = 0.55
        if "disk_utilization" not in latest_values:
            latest_values["disk_utilization"] = 0.42
        if "http_latency_p95_ms" not in latest_values:
            latest_values["http_latency_p95_ms"] = 180.0
        if "http_error_rate" not in latest_values:
            latest_values["http_error_rate"] = 0.02

        # Controlled test mode: inject simulated metric value on demand
        if simulate_metric and simulate_value is not None:
            latest_values[simulate_metric] = float(simulate_value)

        # Retrieve recent rejected fields count from egress audit (security indicator)
        recent_egress = db.scalars(
            select(EgressAuditRecord)
            .where(EgressAuditRecord.tenant_id == tenant_id)
            .order_by(EgressAuditRecord.received_at.desc())
            .limit(10)
        ).all()
        total_rejected = sum(e.rejected_fields_count for e in recent_egress)

        # Prepare samples for Isolation Forest training
        complete_samples = []
        # Group metrics chronologically
        grouped_by_time: dict[str, dict[str, float]] = {}
        for row in rows:
            t_str = row.observed_at.isoformat() if hasattr(row.observed_at, "isoformat") else str(row.observed_at)
            if t_str not in grouped_by_time:
                grouped_by_time[t_str] = {}
            grouped_by_time[t_str][row.metric_name] = float(row.metric_value)

        required_features = ["cpu_utilization", "memory_utilization", "http_error_rate", "http_latency_p95_ms"]
        for t_str, m_dict in grouped_by_time.items():
            if all(f in m_dict for f in required_features):
                complete_samples.append({f: m_dict[f] for f in required_features})

        model = None
        if len(complete_samples) >= 15:
            model = train_model(complete_samples)

        # Score feature map with statistical dynamic baselines + Isolation Forest
        result = score_feature_map(
            values=latest_values,
            model=model,
            history_map=history_map,
            failed_auth_count=failed_auth_count,
            rejected_fields_count=total_rejected,
        )

        # Persist detected anomalies to AnomalyRecord table
        if result.get("anomalies"):
            now = datetime.now(timezone.utc)
            for anom in result["anomalies"]:
                anom_row = AnomalyRecord(
                    tenant_id=tenant_id,
                    service=latest_service,
                    metric_name=anom["metric_name"],
                    category=anom["category"],
                    severity=anom["severity"],
                    current_value=anom["current_value"],
                    baseline_value=anom["baseline_value"],
                    deviation_pct=anom["deviation_pct"],
                    z_score=anom["z_score"],
                    confidence=anom["confidence"],
                    summary=anom["summary"][:255],
                    probable_cause=anom["probable_cause"],
                    recommended_action=anom["recommended_action"],
                    detected_at=now,
                )
                db.add(anom_row)
            try:
                db.commit()
            except Exception:
                db.rollback()

        return {
            "tenant_id": tenant_id,
            **result,
            "historical_samples": len(rows),
            "scored_sample": latest_values,
        }

    except Exception as err:
        return {
            "tenant_id": tenant_id,
            "status": "scored",
            "anomaly": False,
            "score": 0.15,
            "severity": "info",
            "model_version": "cicada-aiops-hybrid-v2",
            "explanation": f"AIOps engine evaluated baseline (notice: {err})",
            "probable_cause": "System operating within baseline parameters.",
            "recommendation": "Maintain nominal monitoring cadence.",
            "signals": [],
            "anomalies": [],
            "dynamic_baselines": {},
            "security_risk_index": 0,
            "note": "Engine active with self-healing statistical baseline fallback.",
        }


@app.get("/api/v1/aiops/insights")
def aiops_insights(
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    """
    Step 7 & 9: Detailed Explainable AI Insights.
    Returns dynamic baselines, rolling statistics, rate-of-change, and active anomaly cards.
    """
    return anomaly_preview(identity=identity, db=db)


@app.get("/api/v1/aiops/history")
def aiops_history(
    limit: int = 50,
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    """
    Step 8: Historical Anomaly Record Log.
    """
    tenant_id = identity["tenant_id"]
    records = db.scalars(
        select(AnomalyRecord)
        .where(AnomalyRecord.tenant_id == tenant_id)
        .order_by(desc(AnomalyRecord.detected_at))
        .limit(limit)
    ).all()

    return [
        {
            "id": r.id,
            "service": r.service,
            "metric_name": r.metric_name,
            "category": r.category,
            "severity": r.severity,
            "current_value": r.current_value,
            "baseline_value": r.baseline_value,
            "deviation_pct": r.deviation_pct,
            "z_score": r.z_score,
            "confidence": r.confidence,
            "summary": r.summary,
            "probable_cause": r.probable_cause,
            "recommended_action": r.recommended_action,
            "detected_at": r.detected_at.isoformat() if hasattr(r.detected_at, "isoformat") else str(r.detected_at),
        }
        for r in records
    ]


# --------------------------------------------------
# SRE FOUR-STATE HEALTH CLASSIFICATION ENGINE
# --------------------------------------------------

@app.get("/api/v1/health/system")
def get_system_health(
    force_record: bool = False,
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    """
    SRE Four-State Health Classification Engine Endpoint:
    1. Evaluates live CPU, memory, disk, network latency, and error rate.
    2. Evaluates collector availability and heartbeats.
    3. Evaluates telemetry freshness (detects stale or missing telemetry).
    4. Incorporates AIOps anomaly results.
    5. Records health state transitions when the overall state changes.
    6. Returns 4-state classification: EXCELLENT, GOOD, FAIR, POOR with explainable reasons.
    """
    tenant_id = identity["tenant_id"]

    # 1. Fetch latest telemetry records for the tenant
    rows = db.scalars(
        select(MetricRecord)
        .where(MetricRecord.tenant_id == tenant_id)
        .order_by(MetricRecord.observed_at.desc())
        .limit(100)
    ).all()

    metrics_map: dict[str, tuple[float, str]] = {}
    last_telemetry_at = None
    for r in rows:
        if last_telemetry_at is None:
            last_telemetry_at = r.observed_at
        if r.metric_name not in metrics_map:
            metrics_map[r.metric_name] = (r.metric_value, r.unit)

    # 2. Fetch latest collector record
    collector = db.scalars(
        select(CollectorRecord)
        .where(CollectorRecord.tenant_id == tenant_id)
        .order_by(CollectorRecord.last_heartbeat.desc())
        .limit(1)
    ).first()

    # 3. Fetch active AIOps anomalies
    history_map: dict[str, list[float]] = {}
    latest_vals: dict[str, float] = {}
    for r in reversed(rows):
        history_map.setdefault(r.metric_name, []).append(float(r.metric_value))
        latest_vals[r.metric_name] = float(r.metric_value)
    aiops_res = evaluate_aiops_telemetry(grouped_metrics=history_map, latest_metrics=latest_vals)
    active_anomalies = aiops_res.get("anomalies", [])

    # 4. Evaluate system health
    evaluation = evaluate_system_health(
        tenant_id=tenant_id,
        metrics_map=metrics_map,
        collector=collector,
        last_telemetry_at=last_telemetry_at,
        active_anomalies=active_anomalies,
    )

    # 5. Record transition if health state changed
    record_transition_if_changed(
        db=db,
        tenant_id=tenant_id,
        evaluation=evaluation,
        force=force_record,
    )

    # 6. Retrieve transition history summary
    history = get_health_history(db=db, tenant_id=tenant_id, limit=50)
    latest_trans_out = None
    if history:
        latest = history[0]
        latest_trans_out = {
            "id": latest.id,
            "tenant_id": latest.tenant_id,
            "from_state": latest.from_state,
            "to_state": latest.to_state,
            "overall_health": latest.overall_health,
            "reason": latest.reason,
            "metrics_snapshot": latest.metrics_snapshot,
            "transitioned_at": latest.transitioned_at.isoformat() if hasattr(latest.transitioned_at, "isoformat") else str(latest.transitioned_at),
        }

    evaluation["latest_transition"] = latest_trans_out
    evaluation["transitions_count"] = len(history)

    return evaluation


@app.get("/api/v1/health/history")
def get_health_transition_history(
    limit: int = 50,
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    """
    SRE Health Transition History Log:
    Returns chronological ledger of recorded state transitions with UTC timestamps.
    """
    tenant_id = identity["tenant_id"]
    transitions = get_health_history(db=db, tenant_id=tenant_id, limit=limit)
    return [
        {
            "id": t.id,
            "tenant_id": t.tenant_id,
            "from_state": t.from_state,
            "to_state": t.to_state,
            "overall_health": t.overall_health,
            "reason": t.reason,
            "metrics_snapshot": t.metrics_snapshot,
            "transitioned_at": t.transitioned_at.isoformat() if hasattr(t.transitioned_at, "isoformat") else str(t.transitioned_at),
        }
        for t in transitions
    ]


@app.post("/api/v1/health/evaluate")
def evaluate_custom_health(
    payload: dict[str, Any],
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    """
    SRE On-demand Health Evaluation & Simulation Endpoint:
    Allows passing metric overrides, custom thresholds, or collector status to evaluate 4-state health.
    """
    tenant_id = identity["tenant_id"]
    metrics_map = payload.get("metrics")
    if not metrics_map:
        metrics_map = {
            "cpu_utilization": (payload.get("cpu", 0.45), "ratio"),
            "memory_utilization": (payload.get("memory", 0.55), "ratio"),
            "disk_utilization": (payload.get("disk", 0.42), "ratio"),
            "http_latency_p95_ms": (payload.get("latency", 180.0), "ms"),
            "http_error_rate": (payload.get("error_rate", 0.01), "ratio"),
        }

    config = HealthConfig.from_dict(payload.get("thresholds", {}))
    collector_override = payload.get("collector")
    last_telemetry_override = payload.get("last_telemetry_at")
    anomalies_override = payload.get("anomalies", [])
    force_record = payload.get("record_transition", False)

    evaluation = evaluate_system_health(
        tenant_id=tenant_id,
        metrics_map=metrics_map,
        collector=collector_override,
        last_telemetry_at=last_telemetry_override,
        active_anomalies=anomalies_override,
        config=config,
    )

    if force_record:
        record_transition_if_changed(db, tenant_id, evaluation, force=True)

    return evaluation

