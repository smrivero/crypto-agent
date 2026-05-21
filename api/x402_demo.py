"""GET /api/v1/premium-demo — thin wrapper over shared x402 payment gate."""

import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from api.x402_payment import (
    apply_settlement_headers,
    attach_expose_headers,
    attach_facilitator_warning,
    require_x402_payment,
    settle_x402_payment,
)

logger = structlog.get_logger(__name__)


async def handle_premium_demo(request: Request) -> Response:
    verified, block = await require_x402_payment(request, "GET /api/v1/premium-demo")
    if block is not None:
        return block

    assert verified is not None

    resp = JSONResponse(
        content={
            "message": "Premium x402 content unlocked",
            "network": "base-sepolia",
            "price":   "0.01 USDC",
        },
    )

    attach_facilitator_warning(resp, verified.facilitator)
    try:
        headers = await settle_x402_payment(verified)
        apply_settlement_headers(resp, headers)
    except Exception as exc:
        logger.exception("premium_demo_settle_failed", error=str(exc))
        attach_expose_headers(resp)

    return resp
