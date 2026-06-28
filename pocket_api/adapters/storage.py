from abc import ABC, abstractmethod
import json
from pathlib import Path


class RunRepository(ABC):
    @abstractmethod
    def save(self, search_id: str, data: dict) -> None: ...

    @abstractmethod
    def load(self, search_id: str) -> dict | None: ...

    @abstractmethod
    def list(self, limit: int = 20) -> list[dict]: ...


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
                result.append({
                    "search_id": data.get("search_id", f.stem),
                    "query": data.get("query", "?"),
                    "created_at": data.get("created_at", "?"),
                    "leads_count": len(data.get("leads", [])),
                    "enriched": data.get("enriched", False),
                })
            except Exception:
                pass
        return result
