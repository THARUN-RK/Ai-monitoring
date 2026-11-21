from __future__ import annotations
import json
import sys
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Resolve policy module safely without namespace collision
try:
    import agent_policy as policy_module
except ImportError:
    try:
        policy_path = Path(__file__).resolve().parent / "policy.py"
        spec = importlib.util.spec_from_file_location("agent_policy", str(policy_path))
        policy_module = importlib.util.module_from_spec(spec)
        sys.modules["agent_policy"] = policy_module
        spec.loader.exec_module(policy_module)
    except Exception:
        from app import policy as policy_module

compute_payload_hash = policy_module.compute_payload_hash
generate_redacted_preview = policy_module.generate_redacted_preview

class EgressProofManager:
    """
    Step 4 - Functional Egress Proof Mechanism.
    Records the exact local event (Panel A), filtering results, approved vs redacted/rejected fields,
    and the exact outbound JSON payload immediately before transmission (Panel B).
    """
    def __init__(self, log_path: str | Path = "data/egress_proof.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.recent_proofs: list[dict[str, Any]] = []

    def record_proof(
        self,
        payload_id: str,
        collector_id: str,
        original_events: list[dict[str, Any]],
        filtered_events: list[dict[str, Any]],
        approved_fields: list[str],
        redacted_fields: list[str],
        rejected_fields: list[str],
        outbound_payload: dict[str, Any],
        delivery_status: str = "pending",
        api_response: Any = None,
        policy_version: str = "v1.0-strict-allowlist",
    ) -> dict[str, Any]:
        """Creates and stores an egress audit proof entry."""
        payload_json = json.dumps(outbound_payload, sort_keys=True, separators=(",", ":"))
        payload_hash = compute_payload_hash(outbound_payload)
        payload_size_bytes = len(payload_json.encode("utf-8"))

        raw_sample = original_events[0] if original_events else {}
        safe_raw_preview = generate_redacted_preview(raw_sample)

        policy_decision = "APPROVED_WITH_REDACTION" if (redacted_fields or rejected_fields) else "APPROVED"

        proof_entry = {
            "payload_id": payload_id,
            "collector_id": collector_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "policy_version": policy_version,
            "policy_decision": policy_decision,
            "payload_hash": payload_hash,
            "payload_size_bytes": payload_size_bytes,
            "original_events_count": len(original_events),
            "approved_fields_count": len(approved_fields),
            "rejected_fields_count": len(rejected_fields) + len(redacted_fields),
            "approved_fields": sorted(list(set(approved_fields))),
            "redacted_fields": sorted(list(set(redacted_fields))),
            "rejected_fields": sorted(list(set(rejected_fields))),
            "raw_sample_redacted": safe_raw_preview,
            "filtered_sample": filtered_events[0] if filtered_events else {},
            "exact_outbound_payload": outbound_payload,
            "exact_outbound_payload_str": json.dumps(outbound_payload, indent=2),
            "delivery_status": delivery_status,
            "api_response": api_response,
        }

        # Keep latest in memory
        self.recent_proofs.insert(0, proof_entry)
        if len(self.recent_proofs) > 100:
            self.recent_proofs.pop()

        # Append to disk log
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(proof_entry) + "\n")
        except Exception:
            pass

        return proof_entry

    def update_delivery(self, payload_id: str, status: str, api_response: Any = None):
        """Updates the delivery status of a recorded egress proof."""
        for p in self.recent_proofs:
            if p["payload_id"] == payload_id:
                p["delivery_status"] = status
                p["api_response"] = api_response
                break

    def get_latest(self, limit: int = 20) -> list[dict[str, Any]]:
        """Returns the most recent egress proofs."""
        return self.recent_proofs[:limit]
