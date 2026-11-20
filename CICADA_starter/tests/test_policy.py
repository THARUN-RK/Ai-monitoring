import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "customer-agent"))
from app.policy import build_approved_metadata

def test_raw_fields_are_not_forwarded():
    event = {
        "observed_at": "2026-11-20T10:00:00Z",
        "metric_name": "cpu_utilization", "value": 0.8, "unit": "ratio",
        "window_seconds": 60, "sample_count": 10,
        "resource": {"service": "api", "environment": "test"},
        "raw_message": "password=hunter2",
        "attributes": {"email": "person@example.com", "token": "secret"},
    }
    result = build_approved_metadata(event)
    assert result is not None
    assert "raw_message" not in result
    assert "attributes" not in result
    assert set(result) == {"observed_at","signal_type","resource","metric","window_seconds","quality"}

def test_unknown_metric_is_rejected():
    event = {"metric_name":"raw_log_export","value":1,
             "resource":{"service":"api","environment":"test"},
             "observed_at":"2026-11-20T10:00:00Z"}
    assert build_approved_metadata(event) is None
