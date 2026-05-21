import json
import time

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from agents.research_agent import CryptoResearchAgent
from api.graph_viz import get_mermaid
from api.request_log import LogEntry, get_recent, record
from api.x402_payment import (
    ROUTE_RESEARCH_PREMIUM,
    summarize_verified_payment,
    apply_settlement_headers,
    attach_facilitator_warning,
    require_x402_payment,
    settle_x402_payment,
)
from config.payment_trace import payment_trace_drain, payment_trace_reset
from api.x402_routes import router as x402_demo_router
from models.schemas import ResearchRequest, ResearchResponse

logger = structlog.get_logger()
router = APIRouter()
router.include_router(x402_demo_router)

_agent: CryptoResearchAgent | None = None


def _get_agent() -> CryptoResearchAgent:
    global _agent
    if _agent is None:
        _agent = CryptoResearchAgent()
    return _agent


# ── Batch endpoint (kept for tests + programmatic use) ────────────────────────

@router.post(
    "/research",
    response_model=ResearchResponse,
    summary="Research a crypto token (batch)",
    tags=["Research"],
)
async def research_token(request_body: ResearchRequest, request: Request) -> Response:
    logger.info("api_request", query=request_body.query, mode=request_body.mode)
    start = time.monotonic()

    verified = None
    if request_body.mode == "premium":
        verified, block = await require_x402_payment(request, ROUTE_RESEARCH_PREMIUM)
        if block is not None:
            return block

    payment_summary = None
    if verified is not None:
        payment_summary = summarize_verified_payment(verified)

    response = await _get_agent().research(
        request_body.query,
        model=request_body.model,
        mode=request_body.mode,
        payment_verified=verified is not None,
        payment_summary=payment_summary,
    )
    elapsed = int((time.monotonic() - start) * 1000)
    record(
        query=request_body.query,
        status="success" if response.success else "error",
        duration_ms=elapsed,
        error=response.error,
    )

    out = JSONResponse(content=response.model_dump(mode="json"))
    if verified is not None:
        attach_facilitator_warning(out, verified.facilitator)
    if request_body.mode == "premium" and verified is not None and response.success:
        headers = await settle_x402_payment(verified)
        apply_settlement_headers(out, headers)
    return out


# ── Streaming endpoint ────────────────────────────────────────────────────────

@router.post(
    "/research/stream",
    summary="Research a crypto token (streaming SSE)",
    tags=["Research"],
)
async def research_stream(request_body: ResearchRequest, request: Request) -> Response:
    """
    Returns a Server-Sent Events stream.  Each event is a JSON object on a
    `data:` line.  The stream ends with `data: [DONE]`.

    Premium mode requires x402 payment on the initial request (PAYMENT-SIGNATURE header).
    """
    payment_trace_reset()
    payment_summary = None
    if request_body.mode == "premium":
        verified, block = await require_x402_payment(request, ROUTE_RESEARCH_PREMIUM)
        if block is not None:
            return block
        assert verified is not None
        payment_summary = summarize_verified_payment(verified)
    else:
        verified = None

    start      = time.monotonic()
    last_event: dict = {}

    async def generate():
        nonlocal last_event
        try:
            if verified is not None and verified.facilitator.warning:
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type":    "payment_log",
                            "step":    "init",
                            "status":  "warn",
                            "message": verified.facilitator.warning,
                        },
                        default=str,
                    )
                    + "\n\n"
                )
            for pe in payment_trace_drain():
                yield f"data: {json.dumps(pe, default=str)}\n\n"

            async for event in _get_agent().astream_research(
                request_body.query,
                model=request_body.model,
                mode=request_body.mode,
                payment_verified=verified is not None,
                payment_summary=payment_summary,
            ):
                last_event = event
                if event.get("type") == "result" and "data" in event:
                    event["data"]["processing_time_ms"] = int((time.monotonic() - start) * 1000)
                yield f"data: {json.dumps(event, default=str)}\n\n"
                for pe in payment_trace_drain():
                    yield f"data: {json.dumps(pe, default=str)}\n\n"
        except Exception as exc:
            err = {"type": "error", "message": str(exc)}
            last_event = err
            yield f"data: {json.dumps(err)}\n\n"
        finally:
            if verified is not None and last_event.get("type") == "result":
                try:
                    headers = await settle_x402_payment(verified)
                    for pe in payment_trace_drain():
                        yield f"data: {json.dumps(pe, default=str)}\n\n"
                    # Settlement headers are not sent over SSE; logged in Payment detail only.
                    _ = headers
                except Exception as exc:
                    logger.exception("stream_settle_failed", error=str(exc))
                    settle_err = {
                        "type":    "payment_log",
                        "step":    "settle",
                        "status":  "error",
                        "message": f"Settlement error: {exc}",
                    }
                    yield f"data: {json.dumps(settle_err)}\n\n"
            for pe in payment_trace_drain():
                yield f"data: {json.dumps(pe, default=str)}\n\n"
            elapsed = int((time.monotonic() - start) * 1000)
            status  = "success" if last_event.get("type") == "result" else "error"
            error   = last_event.get("message") if status == "error" else None
            record(query=request_body.query, status=status, duration_ms=elapsed, error=error)
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Meta endpoints ────────────────────────────────────────────────────────────

@router.get("/logs", response_model=list[LogEntry], summary="Recent request log (dev)", tags=["Meta"])
async def get_logs() -> list[LogEntry]:
    return get_recent()


@router.get("/graph/mermaid", summary="Agent graph as Mermaid diagram", tags=["Meta"])
async def graph_mermaid() -> dict:
    return {"mermaid": get_mermaid()}


@router.get("/health", summary="Health check", tags=["Meta"])
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
