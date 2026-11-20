import hashlib
import hmac
import os
from fastapi import Header, HTTPException

# DEMO ONLY: a single bootstrap credential. Replace with persistent per-agent
# credentials, one-way hashes, expiry, rotation and revocation before deployment.
DEMO_KEY = os.getenv("AGENT_API_KEY", "change-this-demo-key")
DEMO_HASH = hashlib.sha256(DEMO_KEY.encode()).hexdigest()
DEMO_IDENTITIES = {
    DEMO_HASH: {"tenant_id": "demo-tenant", "agent_id": "demo-agent"}
}

def authenticate_agent(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Agent authentication required")
    supplied = authorization.removeprefix("Bearer ").strip()
    supplied_hash = hashlib.sha256(supplied.encode()).hexdigest()
    for stored_hash, identity in DEMO_IDENTITIES.items():
        if hmac.compare_digest(supplied_hash, stored_hash):
            return identity
    raise HTTPException(status_code=401, detail="Invalid agent credential")
