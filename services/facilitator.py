"""
x402 facilitator selection: public (x402.org) or Coinbase CDP.

CDP URL and auth follow cdp-sdk (https://github.com/coinbase/cdp-sdk).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import structlog
from starlette.requests import Request

from config.settings import settings
from x402.http import HTTPFacilitatorClient
from x402.http.facilitator_client import FacilitatorConfig
from x402.http.facilitator_client_base import CreateHeadersAuthProvider

logger = structlog.get_logger(__name__)

FacilitatorMode = Literal["public", "coinbase"]

REQUEST_MODE_HEADER = "X402-Facilitator-Mode"
WARNING_HEADER = "X402-Facilitator-Warning"

COINBASE_UNAVAILABLE_MSG = (
    "Coinbase facilitator unavailable, using public x402 facilitator"
)

_clients: dict[FacilitatorMode, HTTPFacilitatorClient] = {}


@dataclass(frozen=True)
class FacilitatorResolution:
    """Resolved facilitator for one request."""

    requested_mode: FacilitatorMode
    effective_mode: FacilitatorMode
    url: str
    warning: str | None = None


def normalize_facilitator_mode(raw: str | None) -> FacilitatorMode | None:
    if not raw:
        return None
    value = raw.strip().lower()
    if value in ("public", "x402", "x402.org"):
        return "public"
    if value in ("coinbase", "cdp"):
        return "coinbase"
    return None


DEFAULT_FACILITATOR_MODE: FacilitatorMode = "public"


def resolve_facilitator_mode(request: Request | None) -> FacilitatorMode:
    """UI/runtime selection via X402-Facilitator-Mode header; defaults to public."""
    if request is not None:
        header = (
            request.headers.get(REQUEST_MODE_HEADER)
            or request.headers.get(REQUEST_MODE_HEADER.lower())
        )
        parsed = normalize_facilitator_mode(header)
        if parsed is not None:
            return parsed
    return DEFAULT_FACILITATOR_MODE


def public_facilitator_url() -> str:
    url = (settings.x402_public_facilitator_url or "").strip()
    return url or "https://x402.org/facilitator"


def coinbase_credentials_configured() -> bool:
    return bool(
        settings.cdp_api_key_id.strip() and settings.cdp_api_key_secret.strip()
    )


def _build_public_config() -> FacilitatorConfig:
    return FacilitatorConfig(
        url=public_facilitator_url(),
        identifier="public-x402",
    )


def _build_coinbase_config() -> FacilitatorConfig:
    from cdp.x402 import create_facilitator_config

    cdp_cfg = create_facilitator_config(
        settings.cdp_api_key_id.strip() or None,
        settings.cdp_api_key_secret.strip() or None,
    )
    create_headers = cdp_cfg.get("create_headers")
    auth_provider = (
        CreateHeadersAuthProvider(create_headers) if create_headers else None
    )
    return FacilitatorConfig(
        url=cdp_cfg["url"],
        auth_provider=auth_provider,
        identifier="coinbase-cdp",
    )


def _facilitator_config_for_mode(mode: FacilitatorMode) -> FacilitatorConfig:
    if mode == "coinbase":
        return _build_coinbase_config()
    return _build_public_config()


def resolve_facilitator(request: Request | None = None) -> FacilitatorResolution:
    """
    Pick facilitator for this request. Invalid Coinbase config falls back to public.
    """
    requested = resolve_facilitator_mode(request)
    warning: str | None = None
    effective = requested

    if requested == "coinbase":
        if not coinbase_credentials_configured():
            effective = "public"
            warning = COINBASE_UNAVAILABLE_MSG
        else:
            try:
                probe = HTTPFacilitatorClient(_build_coinbase_config())
                probe.get_supported()
            except Exception as exc:
                logger.warning("coinbase_facilitator_unavailable", error=str(exc))
                effective = "public"
                warning = COINBASE_UNAVAILABLE_MSG

    config = _facilitator_config_for_mode(effective)
    return FacilitatorResolution(
        requested_mode=requested,
        effective_mode=effective,
        url=config.url,
        warning=warning,
    )


def get_facilitator(mode: FacilitatorMode | None = None) -> HTTPFacilitatorClient:
    """
    Return a cached HTTPFacilitatorClient for *mode* (default: public).

    Use resolve_facilitator() per request when fallback may apply.
    """
    effective = mode or DEFAULT_FACILITATOR_MODE
    if effective not in _clients:
        config = _facilitator_config_for_mode(effective)
        _clients[effective] = HTTPFacilitatorClient(config)
        logger.info(
            "x402_facilitator_client_ready",
            mode=effective,
            url=config.url,
            identifier=config.identifier,
        )
    return _clients[effective]


def attach_facilitator_warning(response, resolution: FacilitatorResolution) -> None:
    if resolution.warning:
        response.headers[WARNING_HEADER] = resolution.warning


def print_x402_startup_config() -> None:
    """Startup banner (stdout) for operator visibility."""
    wallet = settings.x402_receiving_wallet_address.strip() or "(not set)"
    cdp_ready = coinbase_credentials_configured()
    project = settings.cdp_project_id.strip() or "(not set)"

    print("\n" + "=" * 50)
    print("X402 CONFIG")
    print("=" * 50)
    print("facilitator_selection: UI (dropdown → X402-Facilitator-Mode header)")
    print(f"facilitator_default: {DEFAULT_FACILITATOR_MODE}")
    print(f"public_facilitator_url: {public_facilitator_url()}")
    print(f"coinbase_facilitator_url: {_build_coinbase_config().url}")
    print(f"coinbase_credentials: {'configured' if cdp_ready else 'missing'}")
    print(f"network: {settings.x402_network}")
    print(f"seller_wallet: {wallet}")
    if cdp_ready:
        print(f"project_id: {project}")
    print("=" * 50 + "\n")


def log_payment_event(
    *,
    phase: str,
    facilitator_mode: str,
    facilitator_url: str,
    verify_valid: bool | None = None,
    settlement_id: str | None = None,
    transaction_hash: str | None = None,
    extra: str | None = None,
) -> None:
    parts = [
        f"facilitator={facilitator_mode}",
        f"url={facilitator_url}",
    ]
    if verify_valid is not None:
        parts.append(f"verify={'ok' if verify_valid else 'failed'}")
    if settlement_id:
        parts.append(f"settlement_id={settlement_id}")
    if transaction_hash:
        parts.append(f"tx={transaction_hash}")
    if extra:
        parts.append(extra)
    message = " · ".join(parts)
    print(f"[x402 {phase}] {message}")
    logger.info(
        "x402_payment",
        phase=phase,
        facilitator_mode=facilitator_mode,
        facilitator_url=facilitator_url,
        verify_valid=verify_valid,
        settlement_id=settlement_id,
        transaction_hash=transaction_hash,
        detail=extra,
    )
