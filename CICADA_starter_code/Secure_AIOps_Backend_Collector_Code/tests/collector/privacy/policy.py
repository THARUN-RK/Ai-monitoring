from datetime import datetime, timezone
ALLOWED = {"cpu_percent","memory_percent","disk_percent","network_bytes_sent_rate",
           "network_bytes_recv_rate","uptime_seconds","app_response_ms","app_available"}

def sanitize(records: list[dict]) -> list[dict]:
    clean = []
    for r in records:
        if set(r) - {"server_id","display_name","environment","metric_name","value","unit","observed_at"}:
            raise ValueError("Privacy policy rejected unknown fields")
        if r.get("metric_name") not in ALLOWED:
            raise ValueError("Privacy policy rejected unsupported metric")
        if not isinstance(r.get("value"), (int, float)):
            raise ValueError("Privacy policy rejected invalid metric value")
        clean.append({k: r[k] for k in ("server_id","display_name","environment","metric_name","value","unit","observed_at") if k in r})
    return clean
