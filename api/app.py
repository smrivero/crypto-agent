import pathlib
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config.logging import configure_logging
from config.settings import settings
from api.routes import router

logger = structlog.get_logger()

_ROOT = pathlib.Path(__file__).parent.parent
_STATIC = _ROOT / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(debug=settings.debug)
    logger.info("startup", host=settings.api_host, port=settings.api_port, model=settings.model_name)
    try:
        from api.graph_viz import save_to_docs

        save_to_docs()
        logger.info("mermaid_diagram_saved", path="docs/research_graph.mmd")
    except Exception as exc:
        logger.warning("mermaid_save_failed", error=str(exc))
    try:
        from api.x402_payment import warm_x402_server

        warm_x402_server()
        logger.info("x402_server_warmed")
    except Exception as exc:
        logger.warning("x402_demo_warm_skipped", error=str(exc))
    yield
    logger.info("shutdown")


app = FastAPI(
    title="Crypto Research Agent",
    description="AI-powered cryptocurrency research agent powered by LangGraph.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "PAYMENT-REQUIRED",
        "PAYMENT-RESPONSE",
        "PAYMENT-SIGNATURE",
        "X-PAYMENT",
        "X-PAYMENT-RESPONSE",
        "X402-Facilitator-Warning",
    ],
)

app.mount("/static", StaticFiles(directory=_STATIC), name="static")
app.include_router(router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")
