import time, psutil, platform
_last_net = None
_last_at = None
_started = time.monotonic()

def collect(server_id, display_name, environment):
    global _last_net, _last_at
    now = time.monotonic()
    net = psutil.net_io_counters()
    sent_rate = recv_rate = 0.0
    if _last_net is not None and _last_at is not None and now > _last_at:
        sent_rate = max(0, net.bytes_sent - _last_net.bytes_sent) / (now - _last_at)
        recv_rate = max(0, net.bytes_recv - _last_net.bytes_recv) / (now - _last_at)
    _last_net, _last_at = net, now
    common = {"server_id": server_id, "display_name": display_name, "environment": environment}
    metrics = [
        ("cpu_percent", psutil.cpu_percent(interval=0.2), "%"),
        ("memory_percent", psutil.virtual_memory().percent, "%"),
        ("disk_percent", psutil.disk_usage("/" if platform.system() != "Windows" else "C:\\").percent, "%"),
        ("network_bytes_sent_rate", sent_rate, "bytes/s"),
        ("network_bytes_recv_rate", recv_rate, "bytes/s"),
        ("uptime_seconds", max(0, time.time() - psutil.boot_time()), "seconds"),
    ]
    return [{**common, "metric_name": name, "value": float(value), "unit": unit} for name, value, unit in metrics]
