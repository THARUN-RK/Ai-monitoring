import os, time, logging
from pathlib import Path
import requests
from monitors.system import collect
from privacy.policy import sanitize
from storage.buffer import LocalBuffer
from application.probe import probe

API = os.getenv("CENTRAL_API_URL", "http://127.0.0.1:8000").rstrip("/")
KEY = os.getenv("COLLECTOR_API_KEY", "")
INTERVAL = max(5, int(os.getenv("COLLECTOR_INTERVAL_SECONDS", "15")))
SERVER = os.getenv("COLLECTOR_SERVER_ID", "server-01")
DISPLAY = os.getenv("COLLECTOR_DISPLAY_NAME", "Local Server")
ENV = os.getenv("COLLECTOR_ENVIRONMENT", "development")
logging.basicConfig(filename=os.getenv("LOG_PATH", "./logs/collector.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collector")
buffer = LocalBuffer(os.getenv("BUFFER_PATH", "./buffer"))

def transmit_pending():
    if not KEY:
        log.warning("collector_key_missing; metadata remains buffered")
        return
    for path in buffer.pending():
        try:
            # HTTPS is mandatory for non-loopback hosts.
            if not API.startswith("https://") and not API.startswith(("http://127.0.0.1","http://localhost")):
                raise RuntimeError("HTTPS is required for non-local central API")
            response = requests.post(f"{API}/api/telemetry/ingest",
                json={"records": buffer.read(path)}, headers={"Authorization": f"Bearer {KEY}"},
                timeout=8, verify=True)
            response.raise_for_status()
            buffer.delete(path)
        except Exception as exc:
            log.warning("transmission_failed type=%s", type(exc).__name__)
            break

def run():
    log.info("collector_started interval=%s", INTERVAL)
    while True:
        try:
            records = collect(SERVER, DISPLAY, ENV)
            available, latency = probe(os.getenv("APP_HEALTH_URL", "http://127.0.0.1:8000/api/health"))
            records.extend([
                {"server_id": SERVER, "display_name": DISPLAY, "environment": ENV,
                 "metric_name": "app_available", "value": 1.0 if available else 0.0, "unit": "boolean"},
                {"server_id": SERVER, "display_name": DISPLAY, "environment": ENV,
                 "metric_name": "app_response_ms", "value": latency, "unit": "ms"},
            ])
            approved = sanitize(records)
            buffer.put(approved)
            transmit_pending()
        except Exception as exc:
            log.exception("collection_cycle_failed type=%s", type(exc).__name__)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
