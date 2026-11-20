import re
import os
from typing import Tuple, List, Dict, Any

# Default allowlist – can be extended via env var EGRESS_ALLOWLIST as a comma‑separated list
DEFAULT_ALLOWLIST = {
    "observed_at",
    "metric_name",
    "metric_value",
    "unit",
    "window_seconds",
    "sample_count",
    "service",
    "environment",
    "attributes",
}

ALLOWLIST = set(
    os.getenv("EGRESS_ALLOWLIST", "").split(",")
    if os.getenv("EGRESS_ALLOWLIST")
    else DEFAULT_ALLOWLIST
)

# Regex for keys/values that look like secrets
SENSITIVE_REGEX = re.compile(r"password|secret|api[_-]?key|token|ip|log", re.IGNORECASE)

def _is_sensitive(key: str, value: Any) -> bool:
    """Return True if the key or value appears to be sensitive.
    Any key matching SENSITIVE_REGEX is considered sensitive. Additionally, simple IPv4 patterns in values are redacted.
    """
    if SENSITIVE_REGEX.search(key):
        return True
    if isinstance(value, str) and re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", value):
        return True
    return False

def _redact(value: Any) -> Any:
    """Replace primitive values with a placeholder.
    Complex containers are handled recursively.
    """
    if isinstance(value, (dict, list, tuple)):
        return value
    return "[REDACTED]"

def _walk_and_filter(data: Any, redaction_counter: List[int], kept_fields: List[str]) -> Any:
    """Recursively walk the payload, keep only allow‑listed keys and redact sensitive data.
    Returns a new structure preserving the original shape where possible.
    """
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if k in ALLOWLIST:
                kept_fields.append(k)
                if _is_sensitive(k, v):
                    redaction_counter[0] += 1
                    result[k] = _redact(v)
                else:
                    result[k] = _walk_and_filter(v, redaction_counter, kept_fields)
            else:
                continue
        return result
    if isinstance(data, list):
        return [_walk_and_filter(item, redaction_counter, kept_fields) for item in data]
    return data

def sanitize_payload(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], int, List[str]]:
    """Sanitize the incoming telemetry payload.
    Returns the sanitized payload, the count of redacted fields, and the list of allowed field names retained.
    """
    redaction_counter = [0]
    kept_fields: List[str] = []
    sanitized = _walk_and_filter(raw, redaction_counter, kept_fields)
    return sanitized, redaction_counter[0], kept_fields
