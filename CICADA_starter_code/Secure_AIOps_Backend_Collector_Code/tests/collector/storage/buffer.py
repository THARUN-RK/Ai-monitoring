import json, os, time
from pathlib import Path
class LocalBuffer:
    def __init__(self, directory):
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=True)
    def put(self, records):
        # Only already-sanitized metadata is persisted.
        path = self.directory / f"{int(time.time()*1000)}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(records), encoding="utf-8")
        os.replace(tmp, path)
    def pending(self):
        return sorted(self.directory.glob("*.json"))
    def read(self, path):
        return json.loads(path.read_text(encoding="utf-8"))
    def delete(self, path):
        Path(path).unlink(missing_ok=True)
