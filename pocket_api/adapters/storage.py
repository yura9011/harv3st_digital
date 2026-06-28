from abc import ABC, abstractmethod
import json
from pathlib import Path


class RunRepository(ABC):
    @abstractmethod
    def save(self, search_id: str, data: dict) -> None: ...

    @abstractmethod
    def load(self, search_id: str) -> dict | None: ...


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
