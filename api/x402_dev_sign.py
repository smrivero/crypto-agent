"""
Dev-only: sign x402 payment using EVM_PRIVATE_KEY from .env (DEBUG=true).

Never enable in production. Private key is never logged or returned.
"""

from __future__ import annotations

import structlog
from eth_account import Account
from fastapi import HTTPException
from pydantic import BaseModel, Field

from config.settings import settings
from x402 import x402Client
from x402.http import x402HTTPClient
from x402.http.utils import decode_payment_required_header
from x402.mechanisms.evm.exact import register_exact_evm_client
from x402.mechanisms.evm.signers import EthAccountSigner

from api.x402_payment import caip2_402_network

logger = structlog.get_logger(__name__)

_NETWORK = caip2_402_network()


class DevSignRequest(BaseModel):
    payment_required_header: str = Field(
        ...,
        description="Raw PAYMENT-REQUIRED response header (base64 JSON)",
    )


class DevSignResponse(BaseModel):
    headers: dict[str, str]
    buyer_address: str


async def dev_sign_payment_headers(payment_required_header: str) -> DevSignResponse:
    if not settings.debug:
        raise HTTPException(
            status_code=403,
            detail="Dev sign is only available when DEBUG=true",
        )

    key = settings.evm_private_key.strip()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Set EVM_PRIVATE_KEY in .env for local testnet signing (buyer wallet)",
        )

    header = payment_required_header.strip()
    if not header:
        raise HTTPException(status_code=400, detail="payment_required_header is empty")

    try:
        payment_required = decode_payment_required_header(header)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid PAYMENT-REQUIRED header: {exc}",
        ) from exc

    account = Account.from_key(key)
    signer = EthAccountSigner(account)
    client = x402Client()
    register_exact_evm_client(client, signer, networks=[_NETWORK])
    http_x402 = x402HTTPClient(client)

    try:
        payload = await http_x402.create_payment_payload(payment_required)
        pay_headers = http_x402.encode_payment_signature_header(payload)
    except Exception as exc:
        logger.warning("dev_sign_failed", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"Payment signing failed: {exc}. Check Base Sepolia USDC + ETH on buyer wallet.",
        ) from exc

    logger.info("dev_sign_ok", buyer=account.address)
    return DevSignResponse(headers=pay_headers, buyer_address=account.address)
