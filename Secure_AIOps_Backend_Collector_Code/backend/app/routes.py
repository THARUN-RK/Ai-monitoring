import secrets, logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from .database import get_db
from .models import Organization, User, Collector, Server, Telemetry, Alert, Incident, AuditLog
from .schemas import *
from .security import hash_password, verify_password, create_access_token, current_user, current_collector, hash_collector_key
from .privacy import approve_batch

router = APIRouter(prefix="/api")
log = logging.getLogger("secure_aiops")

def audit(db, org_id, actor_type, actor_id, action, resource_type):
    db.add(AuditLog(organization_id=org_id, actor_type=actor_type, actor_id=str(actor_id),
                    action=action, resource_type=resource_type))

@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "Email already registered")
    org = Organization(name=data.organization_name)
    db.add(org); db.flush()
    user = User(organization_id=org.id, email=email, password_hash=hash_password(data.password), role="admin")
    db.add(user); db.flush()
    audit(db, org.id, "user", user.id, "organization.registered", "organization")
    db.commit()
    return TokenOut(access_token=create_access_token(user), organization=org.name)

@router.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return TokenOut(access_token=create_access_token(user), organization=user.organization.name)

@router.get("/health", response_model=HealthOut)
def health():
    return HealthOut(status="ok", service="secure-aiops-api")

@router.post("/collectors/register", response_model=dict, status_code=201)
def register_collector(data: CollectorRegisterIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in ("admin", "operator"):
        raise HTTPException(403, "Insufficient role")
    raw_key = "cic_" + secrets.token_urlsafe(32)
    collector = Collector(organization_id=user.organization_id, name=data.name,
                          api_key_hash=hash_collector_key(raw_key))
    db.add(collector); db.flush()
    audit(db, user.organization_id, "user", user.id, "collector.registered", "collector")
    db.commit()
    return {"id": collector.id, "name": collector.name, "api_key": raw_key,
            "warning": "Store this key securely; it is shown only once."}

@router.post("/telemetry/ingest", status_code=202)
def ingest(batch: TelemetryBatchIn, collector: Collector = Depends(current_collector), db: Session = Depends(get_db)):
    approved = approve_batch(batch)
    now = datetime.now(timezone.utc)
    inserted = 0
    for item in approved:
        server = db.query(Server).filter(
            Server.organization_id == collector.organization_id,
            Server.collector_id == collector.id,
            Server.external_id == item["server_id"]).first()
        if not server:
            server = Server(organization_id=collector.organization_id, collector_id=collector.id,
                            external_id=item["server_id"], display_name=item["display_name"],
                            environment=item["environment"])
            db.add(server); db.flush()
        db.add(Telemetry(organization_id=collector.organization_id, server_id=server.id,
                         metric_name=item["metric_name"], value=item["value"], unit=item["unit"],
                         observed_at=item["observed_at"]))
        inserted += 1
    collector.last_seen_at = now
    audit(db, collector.organization_id, "collector", collector.id, "telemetry.ingested", "telemetry")
    db.commit()
    return {"accepted": inserted, "status": "accepted"}

@router.get("/telemetry", response_model=list[TelemetryOut])
def list_telemetry(limit: int = Query(100, ge=1, le=1000), user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Telemetry).filter(Telemetry.organization_id == user.organization_id).order_by(desc(Telemetry.observed_at)).limit(limit).all()

@router.get("/collectors", response_model=list[CollectorOut])
def list_collectors(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Collector).filter(Collector.organization_id == user.organization_id).all()

@router.get("/alerts")
def list_alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Alert).filter(Alert.organization_id == user.organization_id).order_by(desc(Alert.created_at)).all()

@router.get("/incidents")
def list_incidents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Incident).filter(Incident.organization_id == user.organization_id).order_by(desc(Incident.created_at)).all()
