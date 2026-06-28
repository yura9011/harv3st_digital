import os
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

AUTH_TOKEN = os.getenv("POCKET_AUTH_TOKEN", "changeme")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "mistralai/mistral-7b-instruct")
security = HTTPBearer(auto_error=False)


async def require_auth(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    token = (credentials.credentials if credentials and credentials.credentials else "").strip()
    if not token or token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token
