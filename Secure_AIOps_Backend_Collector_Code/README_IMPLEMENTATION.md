# Secure AIOps – implementation package (backend + local collector)

This package implements the first executable vertical slice: tenant registration/login,
JWT-protected user APIs, per-collector credentials, tenant-scoped telemetry storage,
strict telemetry schemas, a local allowlist privacy gate, and a Windows/Linux-oriented
psutil collector with a metadata-only local retry buffer.

## 1. Install and run the backend (PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and replace JWT_SECRET and COLLECTOR_API_KEY_PEPPER with random secrets.
uvicorn app.main:app --reload --port 8000
```

Open http://127.0.0.1:8000/docs.

## 2. Run tests

From the package root:

```powershell
python -m pip install -r backend/requirements.txt
python -m pytest -q
```

## 3. Register a tenant and collector

Use Swagger:
1. POST `/api/auth/register` with organization_name, email, and a password of at least 12 characters.
2. Copy the returned `access_token`; click Authorize and enter `Bearer <token>`.
3. POST `/api/collectors/register` with a collector name.
4. Copy the returned collector API key immediately. It is shown once.
5. Configure the local collector's `COLLECTOR_API_KEY` with that value.

## 4. Run the local collector

In a second terminal:

```powershell
cd collector
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:CENTRAL_API_URL="http://127.0.0.1:8000"
$env:COLLECTOR_API_KEY="<paste-one-time-key>"
python main.py
```

The collector stores only allowlisted normalized metrics in its local buffer. It does not collect or transmit raw logs.
For non-loopback central endpoints, the collector refuses plain HTTP and requires HTTPS.

## Security and scope limitations

- This is a hackathon MVP, not a production security certification.
- SQLite `create_all` is used for quick local setup; use Alembic migrations before deployment.
- The first account in a newly registered organization receives the `admin` role. Public self-service organization registration needs abuse controls, email verification, and rate limiting before production.
- JWT uses a shared signing secret. Rotate it securely; production should use a managed secret store and asymmetric signing/key rotation.
- Collector API keys are stored as HMAC hashes; protect the pepper and rotate/revoke keys operationally.
- HTTPS is enforced by the collector for non-loopback destinations, but local development uses loopback HTTP. Production TLS termination, certificate management, mTLS, request replay protection, and network policy still need deployment configuration.
- The collector's retry buffer contains sanitized metadata, not raw logs. Metadata can still leak information through stable server identifiers, precise timestamps, metric combinations, or event patterns. Use pseudonymous IDs, coarser timestamps, retention limits, and tenant-specific policies where required.
- No claim of perfect privacy is made. Allowlisting prevents unapproved fields from being serialized, but cannot prevent inference from approved metadata.
- Application probe is a configurable health URL; the demo defaults to the local API health endpoint.
- Alert/incident list endpoints are tenant-scoped but currently return empty collections until alert/incident generation and lifecycle workflows are added.
- No frontend is included in this phase, by design.
