from abc import ABC, abstractmethod
import json
import time
from pathlib import Path


class RunRepository(ABC):
    @abstractmethod
    def save(self, search_id: str, data: dict) -> None: ...

    @abstractmethod
    def load(self, search_id: str) -> dict | None: ...

    @abstractmethod
    def list(self, limit: int = 20) -> list[dict]: ...

    @abstractmethod
    def find_by_query(self, query: str, near: str | None, max_age_hours: int = 24) -> dict | None: ...


class FileRunRepository(RunRepository):
    def __init__(self, state_dir: str | Path):
        self._dir = Path(state_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, search_id: str) -> Path:
        return self._dir / f"{search_id}.json"

    def save(self, search_id: str, data: dict) -> None:
        self._path(search_id).write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def load(self, search_id: str) -> dict | None:
        p = self._path(search_id)
        if not p.exists():
            return None
        return json.loads(p.read_text())

    def list(self, limit: int = 20) -> list[dict]:
        files = sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        result: list[dict] = []
        for f in files[:limit]:
            try:
                data = json.loads(f.read_text())
                leads = data.get("leads", [])
                audited = sum(1 for l in leads if l.get("analysis"))
                result.append({
                    "search_id": data.get("search_id", f.stem),
                    "query": data.get("query", "?"),
                    "near": data.get("near"),
                    "created_at": data.get("created_at", "?"),
                    "duration_s": data.get("duration_s"),
                    "leads_count": len(leads),
                    "leads_audited": audited,
                    "enriched": data.get("enriched", False),
                })
            except Exception:
                pass
        return result

    def find_by_query(self, query: str, near: str | None, max_age_hours: int = 24) -> dict | None:
        cutoff = time.time() - (max_age_hours * 3600)
        for f in sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(f.read_text())
                if data.get("query") == query and data.get("near") == near:
                    from datetime import datetime
                    created_ts = data.get("created_at", "")
                    try:
                        dt = datetime.strptime(created_ts, "%Y-%m-%d %H:%M:%S")
                        if dt.timestamp() >= cutoff:
                            return data
                    except Exception:
                        return data
            except Exception:
                pass
        return None
