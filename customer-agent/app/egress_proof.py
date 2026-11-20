from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class EgressProofManager:
    """
    Step 4 - Functional Egress Proof Mechanism.
    Records the exact local event, filtering results, approved vs redacted/rejected fields,
    and the exact outbound JSON payload immediately before transmission.
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
    ) -> dict[str, Any]:
        """Creates and stores an egress audit proof entry."""
        proof_entry = {
            "payload_id": payload_id,
            "collector_id": collector_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "original_events_count": len(original_events),
            "original_sample": original_events[0] if original_events else {},
            "filtered_sample": filtered_events[0] if filtered_events else {},
            "approved_fields": sorted(list(set(approved_fields))),
            "redacted_fields": sorted(list(set(redacted_fields))),
            "rejected_fields": sorted(list(set(rejected_fields))),
            "outbound_payload": outbound_payload,
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
