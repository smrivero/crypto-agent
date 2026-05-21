"""x402 routes: premium demo + dev signing (local testnet only)."""

from fastapi import APIRouter, Request

from api.x402_demo import handle_premium_demo
from api.x402_dev_sign import DevSignRequest, DevSignResponse, dev_sign_payment_headers

router = APIRouter(prefix="", tags=["x402"])


@router.get("/premium-demo")
async def premium_demo(request: Request):
    """402 + PAYMENT-REQUIRED without payment; JSON success after signed payment retry."""
    return await handle_premium_demo(request)


@router.post(
    "/x402/dev-sign",
    response_model=DevSignResponse,
    summary="Sign x402 payment (DEBUG + EVM_PRIVATE_KEY only)",
)
async def x402_dev_sign(body: DevSignRequest) -> DevSignResponse:
    """
    Signs PAYMENT-REQUIRED with the buyer wallet from .env.
    Used by the UI to auto-retry premium research without pasting headers manually.
    """
    return await dev_sign_payment_headers(body.payment_required_header)
