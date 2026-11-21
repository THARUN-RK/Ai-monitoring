from __future__ import annotations

import os
import sys
import time
import json
import uuid
import threading
import importlib.util
import requests
from typing import Any, Callable, Optional
from datetime import datetime, timezone
from pathlib import Path

# Resolve policy and buffer modules safely without namespace collision
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

sanitize_event = policy_module.sanitize_event

try:
    import agent_buffer as buffer_module
except ImportError:
    try:
        buf_path = Path(__file__).resolve().parent / "buffer.py"
        spec = importlib.util.spec_from_file_location("agent_buffer", str(buf_path))
        buffer_module = importlib.util.module_from_spec(spec)
        sys.modules["agent_buffer"] = buffer_module
        spec.loader.exec_module(buffer_module)
    except Exception:
        from app import buffer as buffer_module

LocalBuffer = buffer_module.LocalBuffer


class OrganiserStreamConsumer:
    """
    Requirement 2: Shared Organiser Telemetry Stream Integration.
    Connects to external telemetry streams (SSE, WebSocket, or HTTP poll),
    handles automatic reconnection with exponential backoff, validates incoming schemas,
    preserves original source timestamps, deduplicates events, and routes through
    the local Tier 1 privacy filter.
    """

    def __init__(
        self,
        stream_url: Optional[str] = None,
        api_key: Optional[str] = None,
        protocol: Optional[str] = None,
        on_event_received: Optional[Callable[[dict[str, Any]], None]] = None,
        buffer_dir: str = "data/stream_buffer",
        central_api_url: Optional[str] = None,
        central_api_key: Optional[str] = None,
        tenant_id: str = "demo-tenant",
    ):
        self.stream_url = stream_url or os.getenv("ORGANISER_STREAM_URL", "").strip()
        self.api_key = api_key or os.getenv("ORGANISER_STREAM_API_KEY", "").strip()
        self.protocol = (protocol or os.getenv("ORGANISER_STREAM_PROTOCOL", "HTTP_SSE")).upper()
        self.on_event_received = on_event_received
        self.buffer = LocalBuffer(buffer_dir)
        self.central_api_url = (central_api_url or os.getenv("CICADA_API_URL", "http://localhost:8000")).rstrip("/")
        self.central_api_key = central_api_key or os.getenv("CICADA_AGENT_API_KEY", "change-this-demo-key")
        self.tenant_id = tenant_id or os.getenv("TENANT_ID", "demo-tenant")

        # Connection State
        self.status: str = "DISCONNECTED"  # CONNECTED, CONNECTING, RECONNECTING, DISCONNECTED, ERROR
        self.last_event_id: Optional[str] = None
        self.last_event_timestamp: Optional[str] = None
        self.events_received_count: int = 0
        self.duplicate_events_count: int = 0
        self.delayed_events_count: int = 0
        self.reconnect_attempts: int = 0
        self.last_heartbeat: str = datetime.now(timezone.utc).isoformat()
        self.last_error_message: str = ""

        # Deduplication & Sequence Cache
        self._seen_event_ids: set[str] = set()
        self._recent_event_ids_order: list[str] = []
        self._max_seen_cache: int = 50000
        self._last_sequence_num: int = 0

        # Backoff configuration
        self.initial_backoff: float = 1.0
        self.max_backoff: float = 60.0
        self.backoff_factor: float = 2.0
        self.current_backoff: float = self.initial_backoff

        self._running: bool = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Starts the stream consumer background thread if a stream URL is configured."""
        if not self.stream_url:
            self.status = "DISCONNECTED"
            self.last_error_message = "ORGANISER_STREAM_URL not configured. Awaiting organiser connection parameters."
            self.sync_status_to_central()
            return

        self._running = True
        self._thread = threading.Thread(target=self._connection_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stops the consumer loop."""
        self._running = False
        self.status = "DISCONNECTED"
        self.sync_status_to_central()

    def process_incoming_event(self, raw_event: dict[str, Any]) -> tuple[bool, str, Optional[dict[str, Any]]]:
        """
        Validates, deduplicates, and ingests an event received from the organiser stream.
        Preserves original source timestamp.
        """
        self.last_heartbeat = datetime.now(timezone.utc).isoformat()

        # 1. Validate event ID
        event_id = str(raw_event.get("event_id") or raw_event.get("id") or str(uuid.uuid4()))
        if event_id in self._seen_event_ids:
            self.duplicate_events_count += 1
            return False, "duplicate_event_detected", None

        # Add to deduplication sliding cache
        self._seen_event_ids.add(event_id)
        self._recent_event_ids_order.append(event_id)
        if len(self._recent_event_ids_order) > self._max_seen_cache:
            oldest = self._recent_event_ids_order.pop(0)
            self._seen_event_ids.discard(oldest)

        # 2. Extract and preserve timestamps
        source_ts = raw_event.get("source_timestamp") or raw_event.get("timestamp") or raw_event.get("observed_at")
        if not source_ts:
            source_ts = datetime.now(timezone.utc).isoformat()
            raw_event["source_timestamp"] = source_ts
        else:
            raw_event["source_timestamp"] = str(source_ts)

        collector_ts = datetime.now(timezone.utc).isoformat()
        raw_event["collector_timestamp"] = collector_ts
        raw_event["event_id"] = event_id

        # Sequence number handling
        seq_num = raw_event.get("sequence_number")
        if seq_num is None:
            self._last_sequence_num += 1
            raw_event["sequence_number"] = self._last_sequence_num
        else:
            try:
                seq_val = int(seq_num)
                if seq_val <= self._last_sequence_num:
                    raw_event["is_out_of_order"] = True
                self._last_sequence_num = max(self._last_sequence_num, seq_val)
                raw_event["sequence_number"] = seq_val
            except (ValueError, TypeError):
                self._last_sequence_num += 1
                raw_event["sequence_number"] = self._last_sequence_num

        # 3. Privacy filter and allowlist
        sanitized, approved, redacted, rejected = sanitize_event(raw_event)
        if not sanitized:
            return False, "unapproved_or_invalid_metric", None

        self.events_received_count += 1
        self.last_event_id = event_id
        self.last_event_timestamp = str(source_ts)

        if self.on_event_received:
            try:
                self.on_event_received(sanitized)
            except Exception as err:
                print(f"[STREAM DISPATCH ERROR] {err}")

        return True, "accepted", sanitized

    def _connection_loop(self):
        """Persistent connection loop with exponential backoff and error recovery."""
        while self._running:
            try:
                self.status = "CONNECTING"
                self.sync_status_to_central()

                headers = {"Accept": "text/event-stream"}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                print(f"[ORGANISER STREAM] Connecting to {self.stream_url} ({self.protocol})...")
                response = requests.get(self.stream_url, headers=headers, stream=True, timeout=15)

                if response.status_code == 200:
                    self.status = "CONNECTED"
                    self.current_backoff = self.initial_backoff
                    self.last_error_message = ""
                    self.sync_status_to_central()
                    print(f"[ORGANISER STREAM] Connected successfully to {self.stream_url}.")

                    # Stream line by line (SSE protocol)
                    for line in response.iter_lines(decode_unicode=True):
                        if not self._running:
                            break
                        if not line:
                            continue

                        if line.startswith("data:"):
                            raw_payload = line[5:].strip()
                            try:
                                event_data = json.loads(raw_payload)
                                if isinstance(event_data, dict):
                                    self.process_incoming_event(event_data)
                            except json.JSONDecodeError:
                                pass
                else:
                    raise requests.RequestException(f"HTTP {response.status_code}: {response.text[:120]}")

            except Exception as err:
                self.reconnect_attempts += 1
                self.status = "RECONNECTING"
                self.last_error_message = str(err)
                print(f"[ORGANISER STREAM NOTICE] Connection interrupted: {err}. Retrying in {self.current_backoff:.1f}s (attempt {self.reconnect_attempts})...")
                self.sync_status_to_central()

                time.sleep(self.current_backoff)
                self.current_backoff = min(self.max_backoff, self.current_backoff * self.backoff_factor)

    def sync_status_to_central(self):
        """Reports current connection telemetry to the central platform status endpoint."""
        body = {
            "stream_name": "organiser-telemetry-stream",
            "endpoint_url": self.stream_url or "NONE_CONFIGURED",
            "transport_protocol": self.protocol,
            "status": self.status,
            "last_event_id": self.last_event_id,
            "last_event_timestamp": self.last_event_timestamp,
            "events_received_count": self.events_received_count,
            "duplicate_events_count": self.duplicate_events_count,
            "delayed_events_count": self.delayed_events_count,
            "reconnect_attempts": self.reconnect_attempts,
            "last_heartbeat": self.last_heartbeat,
            "error_message": self.last_error_message[:255],
        }
        try:
            requests.post(
                f"{self.central_api_url}/api/v1/stream/status",
                json=body,
                headers={"Authorization": f"Bearer {self.central_api_key}", "Content-Type": "application/json"},
                timeout=5,
            )
        except Exception:
            pass
