import pathlib
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config.logging import configure_logging
from config.settings import settings
from api.routes import router

logger = structlog.get_logger()

_ROOT = pathlib.Path(__file__).parent.parent
_FRONTEND_DIST = _ROOT / "frontend" / "dist"
_LEGACY_STATIC = _ROOT / "static"

_SPA_SKIP_PREFIXES = ("/api/", "/assets/")
_SPA_SKIP_EXACT = frozenset({"/docs", "/openapi.json", "/redoc"})


def _frontend_built() -> bool:
    return (_FRONTEND_DIST / "index.html").is_file()


def _spa_index() -> pathlib.Path:
    built = _FRONTEND_DIST / "index.html"
    if built.is_file():
        return built
    legacy = _LEGACY_STATIC / "index.html"
    if legacy.is_file():
        return legacy
    return built


def _dist_file(relative_path: str) -> pathlib.Path | None:
    if not relative_path or relative_path.endswith("/"):
        return None
    candidate = (_FRONTEND_DIST / relative_path).resolve()
    try:
        candidate.relative_to(_FRONTEND_DIST.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _should_serve_spa(path: str) -> bool:
    if path in _SPA_SKIP_EXACT:
        return False
    return not any(path.startswith(prefix) for prefix in _SPA_SKIP_PREFIXES)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(debug=settings.debug)
    logger.info("startup", host=settings.api_host, port=settings.api_port, model=settings.model_name)
    if _frontend_built():
        logger.info("frontend_static_ready", path=str(_FRONTEND_DIST))
    else:
        logger.warning(
            "frontend_static_missing",
            hint="cd frontend && npm install && npm run build",
        )
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

app.include_router(router, prefix="/api/v1")

if (_FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    spa = _spa_index()
    if not spa.is_file():
        raise HTTPException(
            status_code=503,
            detail="Frontend not built. Run: cd frontend && npm install && npm run build",
        )
    return FileResponse(spa)


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> FileResponse:
    path = f"/{full_path}"
    if not _should_serve_spa(path):
        raise HTTPException(status_code=404)

    static_file = _dist_file(full_path)
    if static_file is not None:
        return FileResponse(static_file)

    spa = _spa_index()
    if not spa.is_file():
        raise HTTPException(
            status_code=503,
            detail="Frontend not built. Run: cd frontend && npm install && npm run build",
        )
    return FileResponse(spa)
