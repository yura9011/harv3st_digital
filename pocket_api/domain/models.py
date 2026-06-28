from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    near: str | None = None
    filters: dict | None = None


def _get(lead: dict, *keys):
    for k in keys:
        v = lead.get(k)
        if v is not None:
            if isinstance(v, str) and v.strip():
                return v.strip()
            if not isinstance(v, str):
                return v
    return None
