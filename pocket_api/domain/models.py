from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    near: str | None = None
    filters: dict | None = None
