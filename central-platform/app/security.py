import hashlib
import hmac
import os
from fastapi import Header, HTTPException

# DEMO ONLY: a single bootstrap credential. Replace with persistent per-agent
# credentials, one-way hashes, expiry, rotation and revocation before deployment.
# Bootstrap credentials for demo and production.
ENV_KEY = os.getenv("AGENT_API_KEY", "change-this-demo-key")
DEFAULT_KEY = "change-this-demo-key"

DEMO_IDENTITIES = {
    hashlib.sha256(DEFAULT_KEY.encode()).hexdigest(): {
        "tenant_id": "demo-tenant",
        "agent_id": "demo-agent",
    },
    hashlib.sha256(ENV_KEY.encode()).hexdigest(): {
        "tenant_id": "demo-tenant",
        "agent_id": "demo-agent",
    },
}

def authenticate_agent(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
):
    supplied = None
    if authorization and authorization.startswith("Bearer "):
        supplied = authorization.removeprefix("Bearer ").strip()
    elif x_api_key:
        supplied = x_api_key.strip()
    elif authorization:
        supplied = authorization.strip()

    if not supplied:
        raise HTTPException(status_code=401, detail="Agent authentication required")

    supplied_hash = hashlib.sha256(supplied.encode()).hexdigest()
    for stored_hash, identity in DEMO_IDENTITIES.items():
        if hmac.compare_digest(supplied_hash, stored_hash):
            return identity
    raise HTTPException(status_code=401, detail="Invalid agent credential")

