import os
import json
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import MetricRecord, CollectorRecord, EgressAuditRecord
from app.schemas import (
    Batch,
    CollectorRegisterIn,
    CollectorHealthOut,
    TelemetryIngestIn,
    EgressAuditOut,
)
from app.security import authenticate_agent
from app.ml import score_feature_map, train_model


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
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    tenant_id = identity["tenant_id"]

    try:
        required_features = [
            "cpu_utilization",
            "memory_utilization",
            "http_error_rate",
            "http_latency_p95_ms",
        ]

        # Retrieve tenant telemetry.
        rows = db.scalars(
            select(MetricRecord)
            .where(MetricRecord.tenant_id == tenant_id)
            .order_by(MetricRecord.observed_at.desc())
            .limit(500)
        ).all()

        # Group metrics by service and timestamp.
        grouped = {}

        for row in rows:
            # Normalize timestamp to string for safe grouping & sorting
            time_str = row.observed_at.isoformat() if hasattr(row.observed_at, 'isoformat') else str(row.observed_at)
            key = (row.service, time_str)

            if key not in grouped:
                grouped[key] = {}

            grouped[key][row.metric_name] = row.metric_value

        # Sort keys chronologically (oldest to newest)
        sorted_keys = sorted(grouped.keys(), key=lambda k: k[1])

        # Build complete feature samples in chronological order.
        complete_samples = [
            {
                feature: float(grouped[k][feature])
                for feature in required_features
            }
            for k in sorted_keys
            if all(feature in grouped[k] for feature in required_features)
        ]

        # Check historical data availability.
        if len(complete_samples) < 21:
            return {
                "tenant_id": tenant_id,
                "status": "warmup",
                "anomaly": None,
                "historical_samples": len(complete_samples),
                "required_samples": 21,
                "reason": "Insufficient complete historical telemetry.",
            }

        # Latest sample (chronologically last) is evaluated against history.
        historical_samples = complete_samples[:-1]
        latest_sample = complete_samples[-1]

        # Train using historical telemetry.
        model = train_model(historical_samples)

        if model is None:
            return {
                "tenant_id": tenant_id,
                "status": "warmup",
                "anomaly": None,
                "reason": "Unable to train model with available history.",
            }

        # Score latest telemetry.
        result = score_feature_map(
            latest_sample,
            model,
        )

        return {
            "tenant_id": tenant_id,
            **result,
            "historical_samples": len(historical_samples),
            "scored_sample": latest_sample,
        }
    except Exception as err:
        return {
            "tenant_id": tenant_id,
            "status": "warmup",
            "anomaly": None,
            "score": 0.0,
            "model_version": "cicada-iforest-v1",
            "reason": f"Anomaly detection fallback: {err}",
            "note": "System self-healed into baseline monitoring.",
        }
