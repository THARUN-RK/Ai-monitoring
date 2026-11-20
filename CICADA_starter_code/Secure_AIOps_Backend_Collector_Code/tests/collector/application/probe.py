import time, requests
def probe(url: str, timeout: float = 3.0) -> tuple[bool, float]:
    start = time.perf_counter()
    try:
        response = requests.get(url, timeout=timeout)
        return response.ok, (time.perf_counter() - start) * 1000
    except requests.RequestException:
        return False, (time.perf_counter() - start) * 1000
