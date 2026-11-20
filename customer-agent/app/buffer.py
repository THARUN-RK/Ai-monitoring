from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Any

class LocalBuffer:
    """
    Step 8 - Atomic disk buffer for offline metadata retention and retry.
    Raw logs are never written to disk; only sanitized telemetry metadata is buffered.
    """
    def __init__(self, directory: str | Path = "data/buffer"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def put(self, payload: dict[str, Any]) -> Path:
        """Atomically saves payload to a temporary file before renaming."""
        timestamp_ms = int(time.time() * 1000)
        final_path = self.directory / f"payload_{timestamp_ms}.json"
        tmp_path = final_path.with_suffix(".tmp")

        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp_path, final_path)
        return final_path

    def pending(self) -> list[Path]:
        """Returns pending buffered payload files in chronological order."""
        return sorted(self.directory.glob("payload_*.json"))

    def read(self, path: Path) -> dict[str, Any]:
        """Reads payload JSON from file."""
        return json.loads(path.read_text(encoding="utf-8"))

    def delete(self, path: Path) -> None:
        """Removes delivered payload file from buffer."""
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    def count(self) -> int:
        """Returns total pending buffered items."""
        return len(self.pending())
