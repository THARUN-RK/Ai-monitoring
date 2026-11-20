from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.egress_audit import EgressAudit

router = APIRouter(prefix="/api/v1/egress", tags=["egress"])

# Internal token for service‑to‑service audit posting (load from env in prod)
AUDIT_TOKEN = "egress_audit_token"

@router.post("/audit")
def post_audit(audit: dict, db: Session = Depends(get_db), x_token: Optional[str] = Header(None, alias="X-Egress-Audit-Token")):
    if x_token != AUDIT_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid audit token")
    record = EgressAudit(
        timestamp=datetime.utcnow(),
        payload_size=audit.get("payload_size", 0),
        dest_endpoint=audit.get("dest_endpoint", ""),
        allowed_fields=audit.get("allowed_fields", []),
        redaction_count=audit.get("redaction_count", 0),
        http_status=audit.get("http_status", 0),
        success=audit.get("success", False),
        sanitized_payload=audit.get("sanitized_payload"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id}

@router.get("/latest")
def get_latest(db: Session = Depends(get_db)):
    row = db.query(EgressAudit).order_by(EgressAudit.timestamp.desc()).first()
    if not row:
        raise HTTPException(status_code=404, detail="No audit records")
    return row

@router.get("/history")
def get_history(limit: int = 20, offset: int = 0, db: Session = Depends(get_db)):
    rows = (
        db.query(EgressAudit)
        .order_by(EgressAudit.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(EgressAudit).count()
    if total == 0:
        return {"total": 0, "success_rate": 0, "avg_payload_size": 0, "total_redactions": 0}
    success = db.query(EgressAudit).filter(EgressAudit.success.is_(True)).count()
    avg_size = db.query(EgressAudit).with_entities(func.avg(EgressAudit.payload_size)).scalar() or 0
    total_redactions = db.query(EgressAudit).with_entities(func.sum(EgressAudit.redaction_count)).scalar() or 0
    return {
        "total": total,
        "success_rate": success / total,
        "avg_payload_size": avg_size,
        "total_redactions": total_redactions,
    }
