# CICADA — Secure AIOps Observability Platform

Hackathon starter with two tiers:
- `customer-agent/`: synthetic telemetry, local policy filtering, explicit metadata projection, HTTPS-capable sender.
- `central-platform/`: FastAPI ingestion, agent authentication, tenant-scoped SQLite persistence, Isolation Forest preview.
- `frontend/`: React + TypeScript + Tailwind dashboard.
- `tests/`: privacy projection tests.

## Run locally (PowerShell)

### Central API
```powershell
cd central-platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:AGENT_API_KEY="change-this-demo-key"
$env:DATABASE_URL="sqlite:///./cicada.db"
uvicorn app.main:app --reload --port 8000
```

### Customer agent — new terminal
```powershell
cd customer-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:CICADA_API_URL="http://localhost:8000"
$env:CICADA_AGENT_API_KEY="change-this-demo-key"
python -m app.main
```

### Frontend — new terminal
```powershell
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173`. API docs: `http://localhost:8000/docs`.

## Important limitations
This is a local hackathon prototype, not production-ready. The demo credential is a shared bootstrap credential; replace it with persistent per-agent credentials, secure provisioning, rotation and revocation. Human-user authentication, role-based authorization, Alembic migrations, durable encrypted local spool, rate limiting, retention, production TLS and security testing remain future work. Do not connect real customer systems or send production data.
