import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))
from privacy.policy import sanitize

def test_allowlist_drops_nothing_and_accepts_only_explicit_shape():
    sample = [{"server_id":"SERVER-01","display_name":"Server","environment":"prod",
               "metric_name":"cpu_percent","value":97,"unit":"%"}]
    assert sanitize(sample)[0]["value"] == 97

def test_unknown_sensitive_fields_fail_closed():
    sample = [{"server_id":"SERVER-01","display_name":"Server","environment":"prod",
               "metric_name":"cpu_percent","value":97,"password":"secret123"}]
    try:
        sanitize(sample)
        assert False, "expected policy rejection"
    except ValueError:
        assert True
