#!/usr/bin/env python3
"""
Local testnet buyer for GET /api/v1/premium-demo (x402 on Base Sepolia).

SECURITY — development only:
  - Set EVM_PRIVATE_KEY in .env for a *test* wallet with Base Sepolia ETH + USDC.
  - Never commit a private key. Never use a mainnet key here.
  - This script does not print secrets (private key is never logged).

Usage:
  uv run python scripts/x402_buyer_test.py

Env:
  EVM_PRIVATE_KEY          — buyer wallet (required)
  X402_DEMO_BASE_URL       — default http://127.0.0.1:8000
  BASE_RPC_URL             — optional Base Sepolia JSON-RPC (balance checks)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import httpx
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3

from x402 import x402Client
from x402.http import PAYMENT_REQUIRED_HEADER, PAYMENT_RESPONSE_HEADER, x402HTTPClient
from x402.http.utils import (
    decode_payment_required_header,
    decode_payment_response_header,
)
from x402.mechanisms.evm.exact import register_exact_evm_client
from x402.mechanisms.evm.signers import EthAccountSigner
from x402.schemas import PaymentRequired

load_dotenv()

# Base Sepolia (CAIP-2 + chain id)
_X402_NETWORK = "eip155:84532"
_CHAIN_ID = 84532
_USDC_ADDRESS = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
_USDC_DECIMALS = 6
_DEFAULT_RPC = "https://base-sepolia-rpc.publicnode.com"

_ERC20_BALANCE_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

_SENSITIVE_HEADER_PREFIXES = ("payment-signature", "x-payment")


def _section(title: str) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


def _pretty_json(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(by_alias=True, exclude_none=True)
    return json.dumps(obj, indent=2, default=str)


def _header_get(headers: httpx.Headers, name: str) -> str | None:
    return headers.get(name) or headers.get(name.lower())


def _decode_payment_required_from_response(
    headers: httpx.Headers,
    body: bytes,
) -> PaymentRequired | None:
    raw = _header_get(headers, PAYMENT_REQUIRED_HEADER)
    if raw:
        try:
            pr = decode_payment_required_header(raw)
            if isinstance(pr, PaymentRequired):
                return pr
            # V1 — still show as dict via model if possible
            print("(PAYMENT-REQUIRED is x402 v1 — showing raw decode)")
            print(_pretty_json(pr))
            return None
        except Exception as exc:
            print(f"Failed to decode PAYMENT-REQUIRED header: {exc}")
            return None

    if body:
        try:
            data = json.loads(body.decode("utf-8"))
            if data.get("x402Version") == 2 and "accepts" in data:
                return PaymentRequired.model_validate(data)
        except Exception:
            pass
    return None


def _print_payment_required(pr: PaymentRequired) -> None:
    print(_pretty_json(pr))
    if pr.accepts:
        req = pr.accepts[0]
        print("\nFirst accepted requirement:")
        print(f"  network:     {req.network}")
        print(f"  scheme:      {req.scheme}")
        print(f"  asset:       {req.asset}")
        print(f"  amount:      {req.amount} (atomic units)")
        print(f"  pay_to:      {req.pay_to}")
        print(f"  max_timeout: {req.max_timeout_seconds}s")
        if req.extra:
            print(f"  extra:       {json.dumps(req.extra, indent=2)}")


def _required_usdc_atomic(pr: PaymentRequired) -> int | None:
    if not pr.accepts:
        return None
    try:
        return int(pr.accepts[0].amount)
    except (TypeError, ValueError):
        return None


def _format_atomic_usdc(amount: int) -> str:
    return f"{amount / 10**_USDC_DECIMALS:.6f} USDC ({amount} atomic)"


def _sanitize_headers_for_print(headers: dict[str, str]) -> dict[str, str]:
    """Show payment header keys and truncated values (never the private key)."""
    out: dict[str, str] = {}
    for k, v in headers.items():
        kl = k.lower()
        if any(kl == p or kl.startswith(p) for p in _SENSITIVE_HEADER_PREFIXES):
            out[k] = f"<base64 len={len(v)} prefix={v[:48]}…>" if len(v) > 48 else v
        else:
            out[k] = v if len(v) <= 200 else f"{v[:200]}… (len={len(v)})"
    return out


def _print_http_response(label: str, resp: httpx.Response) -> None:
    _section(label)
    print(f"status: {resp.status_code}")
    print("\nheaders:")
    for name, value in resp.headers.multi_items():
        display = value
        if name.lower() in (
            PAYMENT_REQUIRED_HEADER.lower(),
            PAYMENT_RESPONSE_HEADER.lower(),
            "payment-signature",
            "x-payment",
        ):
            if len(value) > 80:
                display = f"{value[:80]}… (len={len(value)})"
        print(f"  {name}: {display}")

    print("\nbody:")
    text = resp.text.strip()
    if not text:
        print("  (empty)")
    else:
        try:
            print(_pretty_json(json.loads(text)))
        except json.JSONDecodeError:
            print(text[:4000])

    # Facilitator / settlement hints in headers
    settle_raw = _header_get(resp.headers, PAYMENT_RESPONSE_HEADER)
    if settle_raw:
        print("\nPAYMENT-RESPONSE (decoded):")
        try:
            settle = decode_payment_response_header(settle_raw)
            print(_pretty_json(settle))
            if not getattr(settle, "success", True):
                reason = getattr(settle, "error_reason", None) or getattr(
                    settle, "error_message", None
                )
                print(f"\n*** Facilitator/settlement error: {reason} ***")
        except Exception as exc:
            print(f"  (decode failed: {exc})")


def _connect_web3() -> Web3:
    rpc = os.environ.get("BASE_RPC_URL", _DEFAULT_RPC).strip() or _DEFAULT_RPC
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 15}))
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to Base Sepolia RPC: {rpc}")
    print(f"RPC: {rpc} (chain_id={w3.eth.chain_id})")
    return w3


def _check_balances(w3: Web3, buyer: str, required_atomic: int) -> None:
    _section("Buyer balances (Base Sepolia)")
    checksum_buyer = Web3.to_checksum_address(buyer)
    eth_wei = w3.eth.get_balance(checksum_buyer)
    print(f"  ETH:  {Web3.from_wei(eth_wei, 'ether')} ETH ({eth_wei} wei)")

    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(_USDC_ADDRESS),
        abi=_ERC20_BALANCE_ABI,
    )
    usdc_atomic = usdc.functions.balanceOf(checksum_buyer).call()
    print(f"  USDC: {_format_atomic_usdc(usdc_atomic)}")
    print(f"        token {_USDC_ADDRESS}")
    print(f"  Required: {_format_atomic_usdc(required_atomic)}")

    if usdc_atomic < required_atomic:
        print("\nBuyer wallet needs Base Sepolia USDC")
        sys.exit(1)

    if eth_wei == 0:
        print("\nWarning: ETH balance is 0 — gas may fail during settlement.", file=sys.stderr)


async def main() -> None:
    key = os.environ.get("EVM_PRIVATE_KEY", "").strip()
    if not key:
        print("Missing EVM_PRIVATE_KEY — add it to .env for local testing only.", file=sys.stderr)
        sys.exit(1)

    base = os.environ.get("X402_DEMO_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    url = f"{base}/api/v1/premium-demo"

    account = Account.from_key(key)
    buyer_address = account.address

    _section("Buyer")
    print(f"  address: {buyer_address}")
    print(f"  network: {_X402_NETWORK} (chain_id={_CHAIN_ID})")
    print(f"  asset:   {_USDC_ADDRESS} (Base Sepolia USDC)")

    signer = EthAccountSigner(account)
    client = x402Client()
    register_exact_evm_client(client, signer, networks=[_X402_NETWORK])
    http_x402 = x402HTTPClient(client)

    async with httpx.AsyncClient(timeout=120.0) as h:
        r1 = await h.get(url)
        _print_http_response("First response (expect 402)", r1)

        if r1.status_code == 503:
            print("Server disabled x402 demo — set X402_RECEIVING_WALLET_ADDRESS.", file=sys.stderr)
            sys.exit(1)

        if r1.status_code != 402:
            print("Expected HTTP 402 before payment.", file=sys.stderr)
            sys.exit(1)

        pr = _decode_payment_required_from_response(r1.headers, r1.content)
        _section("PAYMENT-REQUIRED (decoded)")
        if pr is None:
            print("Could not parse payment requirements — cannot continue.")
            sys.exit(1)
        _print_payment_required(pr)

        required_atomic = _required_usdc_atomic(pr)
        if required_atomic is None:
            print("Could not parse required USDC amount from accepts[0].amount", file=sys.stderr)
            sys.exit(1)

        try:
            w3 = _connect_web3()
            _check_balances(w3, buyer_address, required_atomic)
        except ConnectionError as exc:
            print(f"Balance check skipped: {exc}", file=sys.stderr)

        _section("Building payment (x402 client)")
        try:
            pay_headers, payload = await http_x402.handle_402_response(
                dict(r1.headers),
                r1.content,
            )
        except Exception as exc:
            print(f"Payment creation failed: {exc}", file=sys.stderr)
            sys.exit(1)

        print("Payment payload created (not printing full signature blob).")
        if hasattr(payload, "model_dump"):
            dump = payload.model_dump(by_alias=True, exclude_none=True)
            # Omit large signature fields from console
            for key in list(dump.keys()):
                if "signature" in key.lower() and isinstance(dump[key], str) and len(dump[key]) > 80:
                    dump[key] = f"<redacted len={len(dump[key])}>"
            print(_pretty_json(dump))

        _section("Retry request headers")
        print(_pretty_json(_sanitize_headers_for_print(pay_headers)))

        sig = pay_headers.get("PAYMENT-SIGNATURE") or pay_headers.get("payment-signature")
        if sig:
            _section("Browser UI (Premium research)")
            print("Paste this JSON into DevTools or save as sessionStorage key x402_payment_headers:")
            print(json.dumps({"PAYMENT-SIGNATURE": sig}))

        r2 = await h.get(url, headers=pay_headers)
        _print_http_response("Second response (expect 200)", r2)

        if r2.status_code == 402:
            pr2 = _decode_payment_required_from_response(r2.headers, r2.content)
            if pr2 and pr2.error:
                print(f"\n*** Server/facilitator message: {pr2.error} ***")
            print(
                "\nStill 402 after payment — common causes:",
                "\n  - Invalid or expired PAYMENT-SIGNATURE",
                "\n  - Facilitator verify/settle rejected (see PAYMENT-RESPONSE above)",
                "\n  - Insufficient USDC or ETH for gas on buyer wallet",
                "\n  - Wrong network in wallet vs eip155:84532",
                sep="",
            )
            sys.exit(1)

        if r2.status_code != 200:
            sys.exit(1)

        print("\nSuccess: premium content unlocked.")


if __name__ == "__main__":
    asyncio.run(main())
