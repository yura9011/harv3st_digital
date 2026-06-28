import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from pocket_api.api.auth import OPENROUTER_KEY, OPENROUTER_MODEL
from pocket_api.api.routes import router, init_routes
from pocket_api.api.tools import router as tools_router
from pocket_api.domain.scoring import ScoringEngine
from pocket_api.domain.analysis import AnalysisOrchestrator
from pocket_api.adapters.harv3st import Harv3stClient
from pocket_api.adapters.web_checker import WebChecker
from pocket_api.adapters.instagram import InstagramEnricher
from pocket_api.adapters.openrouter import OpenRouterClient
from pocket_api.adapters.storage import FileRunRepository

app = FastAPI(title="FormaDigital Pocket")

HARV3ST_URL = os.getenv("HARV3ST_URL", "http://127.0.0.1:5050")
STATE_DIR = Path(os.getenv("POCKET_STATE_DIR", "/home/yura/formadigital_app/pocket/runs"))

harv3st = Harv3stClient(HARV3ST_URL)
storage = FileRunRepository(STATE_DIR)
scoring_engine = ScoringEngine()
web_checker = WebChecker()
instagram = InstagramEnricher(HARV3ST_URL)
openrouter = OpenRouterClient(OPENROUTER_KEY, OPENROUTER_MODEL) if OPENROUTER_KEY else None
analysis = AnalysisOrchestrator(web_checker, instagram, openrouter)

init_routes(harv3st, storage, scoring_engine, analysis)
app.include_router(router)
app.include_router(tools_router)

FRONTEND_DIR = Path(__file__).parent / "frontend"


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse((FRONTEND_DIR / "index.html").read_text())
