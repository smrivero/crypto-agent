"""
Shared x402 payment gate for protected routes (reused by premium-demo and research).

Seller: X402_RECEIVING_WALLET_ADDRESS — never a private key on the server.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config.payment_trace import payment_trace_emit
from config.settings import settings
from services.facilitator import (
    FacilitatorResolution,
    attach_facilitator_warning,
    get_facilitator,
    log_payment_event,
    public_facilitator_url,
    resolve_facilitator,
)
from x402 import x402ResourceServer
from x402.http import (
    HTTPRequestContext,
    HTTPResponseBody,
    HTTPResponseInstructions,
    PaymentOption,
    PaywallConfig,
    RouteConfig,
    x402HTTPResourceServer,
)
from x402.mechanisms.evm.exact import register_exact_evm_server
from x402.mechanisms.evm.utils import normalize_address
from x402.schemas import PaymentPayload, PaymentRequirements

logger = structlog.get_logger(__name__)

_HTTP_SERVERS: dict[str, x402HTTPResourceServer] = {}

X402_EXPOSE_HEADERS = (
    "PAYMENT-REQUIRED, PAYMENT-RESPONSE, PAYMENT-SIGNATURE, X-PAYMENT, X-PAYMENT-RESPONSE"
)

ROUTE_PREMIUM_DEMO = "GET /api/v1/premium-demo"
# Wildcard covers POST /api/v1/research and POST /api/v1/research/stream
ROUTE_RESEARCH_PREMIUM = "POST /api/v1/research*"


def caip2_402_network() -> str:
    raw = (settings.x402_network or "").strip().lower().replace("_", "-")
    if raw in ("", "base-sepolia"):
        return "eip155:84532"
    if raw.startswith("eip155:"):
        return raw
    raise ValueError(f"Unsupported X402_NETWORK={settings.x402_network!r}")


class StarletteX402Adapter:
    """Minimal x402 HTTPAdapter for Starlette/FastAPI requests."""

    __slots__ = ("_request",)

    def __init__(self, request: Request) -> None:
        self._request = request

    def get_header(self, name: str) -> str | None:
        return self._request.headers.get(name)

    def get_method(self) -> str:
        return self._request.method

    def get_path(self) -> str:
        return self._request.url.path

    def get_url(self) -> str:
        return str(self._request.url)

    def get_accept_header(self) -> str:
        return self._request.headers.get("accept") or ""

    def get_user_agent(self) -> str:
        return self._request.headers.get("user-agent") or ""

    def get_query_params(self) -> dict[str, str | list[str]] | None:
        q = self._request.query_params
        if not q:
            return None
        out: dict[str, str | list[str]] = {}
        for k in q.keys():
            vals = q.getlist(k)
            out[k] = vals if len(vals) > 1 else vals[0]
        return out

    def get_query_param(self, name: str) -> str | list[str] | None:
        if name not in self._request.query_params:
            return None
        vals = self._request.query_params.getlist(name)
        return vals if len(vals) > 1 else vals[0]

    def get_body(self) -> Any:
        return None


def attach_expose_headers(resp: Response) -> None:
    resp.headers["Access-Control-Expose-Headers"] = X402_EXPOSE_HEADERS


def instructions_to_response(instr: HTTPResponseInstructions) -> Response:
    h = {k: str(v) for k, v in instr.headers.items()}
    if instr.is_html:
        body = instr.body if isinstance(instr.body, str) else str(instr.body)
        out = Response(content=body, status_code=instr.status, headers=h)
        attach_expose_headers(out)
        return out
    if isinstance(instr.body, (dict, list)):
        out = JSONResponse(content=instr.body, status_code=instr.status, headers=h)
        attach_expose_headers(out)
        return out
    if instr.body is None:
        out = Response(status_code=instr.status, headers=h)
        attach_expose_headers(out)
        return out
    if isinstance(instr.body, str):
        out = Response(content=instr.body, status_code=instr.status, headers=h)
        attach_expose_headers(out)
        return out
    out = Response(
        content=json.dumps(instr.body, default=str),
        status_code=instr.status,
        media_type=h.get("Content-Type", "application/json"),
        headers=h,
    )
    attach_expose_headers(out)
    return out


def _unpaid_body(_ctx: HTTPRequestContext, *, context: str) -> HTTPResponseBody:
    return HTTPResponseBody(
        content_type="application/json",
        body={
            "error":           "payment_required",
            "message":         context,
            "network":         "base-sepolia",
            "caip2":           caip2_402_network(),
            "facilitator_url": public_facilitator_url(),
            "price":           settings.x402_demo_price,
            "hint": (
                "Send PAYMENT-SIGNATURE on retry after signing with a Base Sepolia wallet "
                "(USDC + ETH for gas). See scripts/x402_buyer_test.py."
            ),
        },
    )


def _payment_route_config(description: str, unpaid_message: str) -> RouteConfig:
    pay_to = normalize_address(settings.x402_receiving_wallet_address.strip())
    return RouteConfig(
        accepts=PaymentOption(
            scheme="exact",
            pay_to=pay_to,
            price=settings.x402_demo_price,
            network=caip2_402_network(),
        ),
        description=description,
        mime_type="application/json",
        unpaid_response_body=lambda ctx: _unpaid_body(ctx, context=unpaid_message),
    )


def _build_x402_http_server(resolution: FacilitatorResolution) -> x402HTTPResourceServer:
    facilitator = get_facilitator(resolution.effective_mode)
    resource = x402ResourceServer(facilitator)
    register_exact_evm_server(resource, networks=[caip2_402_network()])
    resource.initialize()

    routes = {
        ROUTE_PREMIUM_DEMO: _payment_route_config(
            "Premium x402 demo (Base Sepolia testnet)",
            "Premium demo requires x402 payment on Base Sepolia (USDC).",
        ),
        ROUTE_RESEARCH_PREMIUM: _payment_route_config(
            "Premium crypto research (Base Sepolia testnet)",
            "Premium research requires x402 payment on Base Sepolia (USDC).",
        ),
    }
    return x402HTTPResourceServer(resource, routes)


def get_x402_http_server(resolution: FacilitatorResolution) -> x402HTTPResourceServer:
    key = resolution.effective_mode
    if key not in _HTTP_SERVERS:
        _HTTP_SERVERS[key] = _build_x402_http_server(resolution)
    return _HTTP_SERVERS[key]


def warm_x402_server() -> None:
    from services.facilitator import print_x402_startup_config

    print_x402_startup_config()
    if settings.x402_receiving_wallet_address.strip():
        resolution = resolve_facilitator(None)
        get_x402_http_server(resolution)
        logger.info(
            "x402_server_ready",
            mode=resolution.effective_mode,
            facilitator=resolution.url,
        )


def x402_disabled_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error":   "x402_disabled",
            "message": "Set X402_RECEIVING_WALLET_ADDRESS in .env to enable premium payments.",
        },
    )


@dataclass
class X402VerifiedPayment:
    """Payment verified; run protected handler then call settle()."""

    http_server: x402HTTPResourceServer
    ctx: HTTPRequestContext
    payment_payload: PaymentPayload
    payment_requirements: PaymentRequirements
    facilitator: FacilitatorResolution


def _response_with_warning(
    response: Response,
    resolution: FacilitatorResolution,
) -> Response:
    attach_facilitator_warning(response, resolution)
    return response


def _payment_header_present(request: Request) -> bool:
    for name in ("PAYMENT-SIGNATURE", "payment-signature", "X-PAYMENT", "x-payment"):
        if request.headers.get(name):
            return True
    return False


def summarize_verified_payment(verified: X402VerifiedPayment) -> dict[str, str]:
    raw = verified.payment_payload.payload
    auth = raw.get("authorization", raw) if isinstance(raw, dict) else {}
    if not isinstance(auth, dict):
        auth = {}
    req = verified.payment_requirements
    return {
        "payer":   str(auth.get("from", "?")),
        "pay_to":  str(auth.get("to", "?")),
        "amount":  str(auth.get("value", "?")),
        "network": str(getattr(req, "network", "?")),
        "asset":   str(getattr(req, "asset", "?")),
        "scheme":  str(getattr(req, "scheme", "?")),
    }


async def require_x402_payment(
    request: Request,
    route_pattern: str,
) -> tuple[X402VerifiedPayment | None, Response | None]:
    """
    Verify x402 payment for *route_pattern* (e.g. POST /api/v1/research).

    Returns (verified, None) on success, or (None, error_response) on 402/503/500.
    """
    payment_trace_emit(
        "config",
        "Checking seller configuration (X402_RECEIVING_WALLET_ADDRESS)",
        status="info",
    )
    if not settings.x402_receiving_wallet_address.strip():
        payment_trace_emit(
            "config",
            "x402 disabled — seller address missing",
            status="error",
        )
        return None, x402_disabled_response()

    payment_trace_emit(
        "config",
        f"Seller configured · network {caip2_402_network()} · price {settings.x402_demo_price}",
        status="ok",
    )

    resolution = resolve_facilitator(request)

    try:
        payment_trace_emit(
            "init",
            f"Initializing x402 server ({resolution.effective_mode} · {resolution.url})",
            status="info",
        )
        http_server = get_x402_http_server(resolution)
        if resolution.warning:
            payment_trace_emit("init", resolution.warning, status="warn")
        payment_trace_emit("init", "x402 server ready", status="ok")
    except Exception as exc:
        logger.exception("x402_init_failed")
        payment_trace_emit("init", f"Failed to start x402: {exc}", status="error")
        return None, _response_with_warning(
            JSONResponse(
                status_code=500,
                content={"error": "x402_init_failed", "message": str(exc)},
            ),
            resolution,
        )

    if _payment_header_present(request):
        payment_trace_emit(
            "headers",
            "PAYMENT-SIGNATURE header received — verifying with facilitator",
            status="info",
        )
    else:
        payment_trace_emit(
            "headers",
            "No PAYMENT-SIGNATURE — client must sign and retry (HTTP 402)",
            status="warn",
        )

    adapter = StarletteX402Adapter(request)
    ctx = HTTPRequestContext(
        adapter=adapter,
        path=adapter.get_path(),
        method=adapter.get_method(),
    )

    payment_trace_emit(
        "verify",
        f"Verifying payment for {route_pattern}",
        status="info",
        detail=f"{request.method} {request.url.path}",
    )
    result = await http_server.process_http_request(
        ctx,
        paywall_config=PaywallConfig(
            testnet=True,
            app_name="Crypto Research Agent",
        ),
    )

    if result.type == "payment-error" and result.response:
        payment_trace_emit(
            "verify",
            "Payment required or rejected (402 / payment-error)",
            status="warn",
        )
        resp = instructions_to_response(result.response)
        attach_facilitator_warning(resp, resolution)
        return None, _response_with_warning(resp, resolution)

    if result.type == "no-payment-required":
        logger.warning(
            "x402_route_not_matched",
            method=request.method,
            path=request.url.path,
            expected_pattern=route_pattern,
        )
        payment_trace_emit(
            "verify",
            f"No matching x402 route (expected {route_pattern})",
            status="error",
        )
        return None, _response_with_warning(
            JSONResponse(
                status_code=500,
                content={
                    "error":   "x402_route_not_matched",
                    "message": f"No x402 payment route for {request.method} {request.url.path}",
                    "detail":  result.type,
                    "hint":    f"Register path under pattern {route_pattern!r}",
                },
            ),
            resolution,
        )

    if result.type != "payment-verified":
        payment_trace_emit(
            "verify",
            f"Unexpected facilitator response: {result.type}",
            status="error",
        )
        return None, _response_with_warning(
            JSONResponse(
                status_code=500,
                content={"error": "x402_unexpected", "detail": result.type},
            ),
            resolution,
        )

    if result.payment_payload is None or result.payment_requirements is None:
        payment_trace_emit(
            "verify",
            "Incomplete verification — missing payload or requirements",
            status="error",
        )
        return None, _response_with_warning(
            JSONResponse(
                status_code=500,
                content={"error": "x402_internal", "message": "Missing payment after verify"},
            ),
            resolution,
        )

    verified = X402VerifiedPayment(
        http_server=http_server,
        ctx=ctx,
        payment_payload=result.payment_payload,
        payment_requirements=result.payment_requirements,
        facilitator=resolution,
    )
    summary = summarize_verified_payment(verified)
    log_payment_event(
        phase="verify",
        facilitator_mode=resolution.effective_mode,
        facilitator_url=resolution.url,
        verify_valid=True,
        extra=f"payer={summary['payer']} amount={summary['amount']}",
    )
    payment_trace_emit(
        "verify",
        "Payment verified by facilitator",
        status="ok",
        detail=(
            f"facilitator={resolution.effective_mode} · "
            f"payer={summary['payer']} · amount={summary['amount']} atomic · "
            f"network={summary['network']}"
        ),
    )
    return verified, None


async def settle_x402_payment(verified: X402VerifiedPayment) -> dict[str, str]:
    """Settle after successful resource delivery. Returns response headers to merge."""
    summary = summarize_verified_payment(verified)
    resolution = verified.facilitator
    payment_trace_emit(
        "settle",
        "Settling payment with facilitator (on-chain settlement)",
        status="info",
        detail=(
            f"facilitator={resolution.effective_mode} · "
            f"amount={summary['amount']} · pay_to={summary['pay_to']}"
        ),
    )
    try:
        settle = await verified.http_server.process_settlement(
            verified.payment_payload,
            verified.payment_requirements,
            verified.ctx,
        )
    except Exception as exc:
        logger.exception("x402_settle_exception")
        log_payment_event(
            phase="settle",
            facilitator_mode=resolution.effective_mode,
            facilitator_url=resolution.url,
            verify_valid=None,
            extra=f"exception={exc}",
        )
        payment_trace_emit("settle", f"Settlement exception: {exc}", status="error")
        raise

    tx_hash = settle.transaction
    settlement_id = settle.headers.get("X-Settlement-Id") or settle.headers.get(
        "x-settlement-id"
    )

    if not settle.success:
        reason = settle.error_reason or "unknown"
        log_payment_event(
            phase="settle",
            facilitator_mode=resolution.effective_mode,
            facilitator_url=resolution.url,
            verify_valid=False,
            settlement_id=settlement_id,
            transaction_hash=tx_hash,
            extra=f"reason={reason}",
        )
        logger.warning("x402_settle_failed", reason=reason)
        payment_trace_emit(
            "settle",
            f"Settlement failed: {reason}",
            status="warn",
        )
        return dict(settle.headers)

    log_payment_event(
        phase="settle",
        facilitator_mode=resolution.effective_mode,
        facilitator_url=resolution.url,
        verify_valid=True,
        settlement_id=settlement_id,
        transaction_hash=tx_hash,
        extra=f"payer={summary['payer']}",
    )
    payment_trace_emit(
        "settle",
        "Settlement complete — USDC transferred to seller",
        status="ok",
        detail=(
            f"facilitator={resolution.effective_mode} · "
            f"tx={tx_hash or '—'} · payer={summary['payer']}"
        ),
    )
    return dict(settle.headers)


def apply_settlement_headers(response: Response, headers: dict[str, str]) -> None:
    for k, v in headers.items():
        if v is None:
            continue
        response.headers[str(k)] = str(v)
    attach_expose_headers(response)
