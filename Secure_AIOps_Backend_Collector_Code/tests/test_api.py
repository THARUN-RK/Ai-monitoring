import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ["DATABASE_URL"] = "sqlite:///./test_secure_aiops.db"
os.environ["JWT_SECRET"] = "test-secret-change-this-to-a-long-value"
os.environ["COLLECTOR_API_KEY_PEPPER"] = "test-pepper"
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine

def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def test_register_health_and_tenant_scoped_lists():
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        r = client.post("/api/auth/register", json={
            "organization_name":"Bank Alpha", "email":"admin@alpha.test", "password":"StrongPassword123!"
        })
        assert r.status_code == 201
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/collectors", headers=h).json() == []
        assert client.get("/api/telemetry", headers=h).json() == []

def test_collector_ingestion_and_unauthorized_rejection():
    with TestClient(app) as client:
        r = client.post("/api/auth/register", json={
            "organization_name":"Bank Beta", "email":"admin@beta.test", "password":"StrongPassword123!"
        })
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        c = client.post("/api/collectors/register", headers=h, json={"name":"collector-1"})
        assert c.status_code == 201
        key = c.json()["api_key"]
        payload = {"records":[{"server_id":"s-1","display_name":"Server 1","environment":"test",
            "metric_name":"cpu_percent","value":87.5,"unit":"%"}]}
        assert client.post("/api/telemetry/ingest", json=payload,
            headers={"Authorization":f"Bearer {key}"}).status_code == 202
        assert client.get("/api/telemetry", headers=h).status_code == 200
        assert client.post("/api/telemetry/ingest", json=payload).status_code == 401

def test_privacy_schema_rejects_unknown_fields():
    with TestClient(app) as client:
        r = client.post("/api/auth/register", json={
            "organization_name":"Gamma", "email":"admin@gamma.test", "password":"StrongPassword123!"
        })
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        c = client.post("/api/collectors/register", headers=h, json={"name":"c"})
        key = c.json()["api_key"]
        payload = {"records":[{"server_id":"s","display_name":"S","environment":"prod",
            "metric_name":"cpu_percent","value":10,"password":"should-not-pass"}]}
        assert client.post("/api/telemetry/ingest", json=payload,
            headers={"Authorization":f"Bearer {key}"}).status_code == 422
