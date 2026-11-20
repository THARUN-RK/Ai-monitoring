from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import Base, engine, get_db
from app.egress_audit import EgressAudit
from app.models import MetricRecord
from app.schemas import Batch
from app.security import authenticate_agent
from app.ml import score_feature_map

Base.metadata.create_all(bind=engine)
app = FastAPI(title="CICADA Secure AIOps API", version="0.1.0")
# Local-development CORS only. Restrict this list to your deployed UI origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.get("/api/v1/health/live")
def live():
    return {"status": "alive"}

@app.post("/api/v1/agent/batches", status_code=202)
def ingest_batch(batch: Batch, identity=Depends(authenticate_agent), db: Session = Depends(get_db)):
    tenant_id = identity["tenant_id"]  # Derived from credential, never request JSON.
    agent_id = identity["agent_id"]

    existing = db.scalar(select(MetricRecord).where(
        MetricRecord.tenant_id == tenant_id,
        MetricRecord.batch_id == batch.batch_id
    ).limit(1))
    if existing:
        return {"batch_id": batch.batch_id, "status": "duplicate", "accepted_records": 0}

    rows = [
        MetricRecord(
            tenant_id=tenant_id, agent_id=agent_id, batch_id=batch.batch_id,
            event_id=r.event_id, observed_at=r.observed_at.replace(tzinfo=None),
            service=r.resource.service, environment=r.resource.environment,
            metric_name=r.metric.name, metric_value=r.metric.value, unit=r.metric.unit,
            window_seconds=r.window_seconds, sample_count=r.quality.sample_count,
        ) for r in batch.records
    ]
    try:
        db.add_all(rows)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Batch conflicts with existing data")
    return {"batch_id": batch.batch_id, "status": "accepted", "accepted_records": len(rows)}

@app.get("/api/v1/dashboard/summary")
def dashboard_summary(identity=Depends(authenticate_agent), db: Session = Depends(get_db)):
    tenant_id = identity["tenant_id"]
    rows = db.scalars(
        select(MetricRecord).where(MetricRecord.tenant_id == tenant_id)
        .order_by(MetricRecord.observed_at.desc()).limit(100)
    ).all()
    latest = {}
    for row in rows:
        latest.setdefault(row.metric_name, row.metric_value)
    return {
        "tenant_id": tenant_id, "records_returned": len(rows),
        "latest_metrics": latest,
        "records": [{
            "observed_at": r.observed_at.isoformat(), "service": r.service,
            "environment": r.environment, "metric_name": r.metric_name,
            "metric_value": r.metric_value, "unit": r.unit
        } for r in rows]
    }

@app.get("/api/v1/anomalies/preview")
def anomaly_preview(identity=Depends(authenticate_agent), db: Session = Depends(get_db)):
    tenant_id = identity["tenant_id"]
    rows = db.scalars(
        select(MetricRecord).where(MetricRecord.tenant_id == tenant_id)
        .order_by(MetricRecord.observed_at.desc()).limit(100)
    ).all()
    latest = {}
    for row in rows:
        latest.setdefault(row.metric_name, row.metric_value)
    return {"tenant_id": tenant_id, **score_feature_map(latest)}
