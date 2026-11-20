import os
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import MetricRecord
from app.schemas import Batch
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
    version="0.1.0",
    description="Privacy-preserving AI-powered observability platform",
)


# --------------------------------------------------
# CORS CONFIGURATION
# ALLOWED_ORIGINS env var: comma-separated list of allowed origins.
# Set to "*" on Render to allow all origins (update once you know your
# frontend URL, e.g. https://my-app.onrender.com).
# --------------------------------------------------

_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
if _raw_origins.strip() == "*":
    _allow_origins = ["*"]
else:
    _allow_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
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
# TELEMETRY INGESTION
# --------------------------------------------------

@app.post("/api/v1/agent/batches", status_code=202)
def ingest_batch(
    batch: Batch,
    identity=Depends(authenticate_agent),
    db: Session = Depends(get_db),
):
    tenant_id = identity["tenant_id"]
    agent_id = identity["agent_id"]

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

    return {
        "tenant_id": tenant_id,
        "records_returned": len(rows),
        "latest_metrics": latest,
        "records": [
            {
                "observed_at": record.observed_at.isoformat(),
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
        key = (
            row.service,
            row.observed_at,
        )

        if key not in grouped:
            grouped[key] = {}

        grouped[key][row.metric_name] = row.metric_value

    # Build complete feature samples.
    complete_samples = [
        {
            feature: float(metrics[feature])
            for feature in required_features
        }
        for metrics in grouped.values()
        if all(feature in metrics for feature in required_features)
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

    # Latest sample is evaluated separately.
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
