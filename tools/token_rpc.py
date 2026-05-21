"""
ERC-20 on-chain metadata fetcher.

Priority for RPC URL:
  1. Environment variable (ETHEREUM_RPC_URL, BASE_RPC_URL, etc.)
  2. Public fallback (publicnode.com)

Holder count requires a block-explorer API key; returns null otherwise.
Retries up to 3 total attempts before giving up (never raises).
"""

import asyncio
import os

import httpx
import structlog

from config.settings import settings
from config.stream_trace import trace_emit

logger = structlog.get_logger()

# ── Network registry ──────────────────────────────────────────────────────────

_NETWORKS: dict[str, dict] = {
    "ethereum": {
        "chain_id":    1,
        "rpc_env":     "ETHEREUM_RPC_URL",
        "rpc_fallback": "https://ethereum-rpc.publicnode.com",
        "explorer_env": "ETHERSCAN_API_KEY",
        "explorer_api": "https://api.etherscan.io/api",
    },
    "base": {
        "chain_id":    8453,
        "rpc_env":     "BASE_RPC_URL",
        "rpc_fallback": "https://base-rpc.publicnode.com",
        "explorer_env": "BASESCAN_API_KEY",
        "explorer_api": "https://api.basescan.org/api",
    },
    "polygon": {
        "chain_id":    137,
        "rpc_env":     "POLYGON_RPC_URL",
        "rpc_fallback": "https://polygon-rpc.publicnode.com",
        "explorer_env": "POLYGONSCAN_API_KEY",
        "explorer_api": "https://api.polygonscan.com/api",
    },
    "arbitrum": {
        "chain_id":    42161,
        "rpc_env":     "ARBITRUM_RPC_URL",
        "rpc_fallback": "https://arbitrum-one-rpc.publicnode.com",
        "explorer_env": "ARBISCAN_API_KEY",
        "explorer_api": "https://api.arbiscan.io/api",
    },
}

# Fallback gratuito (holders) cuando Etherscan tokeninfo/tokenholdercount exige API Pro.
_BLOCKSCOUT_API: dict[str, str] = {
    "ethereum": "https://eth.blockscout.com",
    "base":       "https://base.blockscout.com",
    "polygon":    "https://polygon.blockscout.com",
    "arbitrum":   "https://arbitrum.blockscout.com",
}

# Etherscan API v2 — una sola API key + chainid para todas las redes soportadas.
_ETHERSCAN_V2_API = "https://api.etherscan.io/v2/api"

_EXPLORER_SETTINGS: dict[str, str] = {
    "ethereum": "etherscan_api_key",
    "base":       "basescan_api_key",
    "polygon":    "polygonscan_api_key",
    "arbitrum":   "arbiscan_api_key",
}


def _explorer_api_key(network: str) -> tuple[str, bool]:
    """
    Devuelve (api_key, use_v2_unified).

    Si solo hay ETHERSCAN_API_KEY, se usa API v2 con chainid de la red.
    """
    field = _EXPLORER_SETTINGS.get(network)
    if field:
        specific = getattr(settings, field, "").strip()
        if specific:
            return specific, False

    unified = settings.etherscan_api_key.strip()
    if unified:
        return unified, True

    cfg = _NETWORKS[network]
    return os.getenv(cfg["explorer_env"], "").strip(), False


def _explorer_env_label(network: str) -> str:
    _, use_v2 = _explorer_api_key(network)
    if use_v2:
        return "ETHERSCAN_API_KEY (v2 multichain)"
    return _NETWORKS[network]["explorer_env"]


# ── Minimal ERC-20 ABI ────────────────────────────────────────────────────────

_ERC20_ABI = [
    {"name": "name",        "type": "function", "inputs": [], "outputs": [{"type": "string"}],  "stateMutability": "view"},
    {"name": "symbol",      "type": "function", "inputs": [], "outputs": [{"type": "string"}],  "stateMutability": "view"},
    {"name": "decimals",    "type": "function", "inputs": [], "outputs": [{"type": "uint8"}],   "stateMutability": "view"},
    {"name": "totalSupply", "type": "function", "inputs": [], "outputs": [{"type": "uint256"}], "stateMutability": "view"},
]


def _rpc_url(network: str) -> tuple[str, bool]:
    """Return (url, is_fallback) for the given network."""
    cfg     = _NETWORKS[network]
    env_url = os.getenv(cfg["rpc_env"], "").strip()
    if env_url:
        return env_url, False
    return cfg["rpc_fallback"], True


def _fetch_erc20_sync(contract_address: str, network: str) -> dict:
    """Synchronous Web3 call — run inside asyncio.to_thread."""
    from web3 import Web3  # lazy import so the module loads without web3 installed

    rpc_url, is_fallback = _rpc_url(network)
    cfg = _NETWORKS[network]

    logger.info(
        "rpc_connect",
        network=network,
        rpc=rpc_url,
        fallback=is_fallback,
        contract=contract_address,
    )

    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to {network} RPC at {rpc_url}")

    checksum = Web3.to_checksum_address(contract_address)
    contract = w3.eth.contract(address=checksum, abi=_ERC20_ABI)

    name         = contract.functions.name().call()
    symbol       = contract.functions.symbol().call()
    decimals     = contract.functions.decimals().call()
    total_supply = contract.functions.totalSupply().call()

    divisor   = 10 ** max(decimals, 0)
    formatted = total_supply / divisor

    return {
        "network":                network,
        "chain_id":               cfg["chain_id"],
        "contract_address":       checksum,
        "token_name":             name,
        "token_symbol":           symbol,
        "decimals":               decimals,
        "total_supply_raw":       str(total_supply),
        "total_supply_formatted": f"{formatted:,.2f}",
        "rpc_url":                rpc_url,
        "rpc_fallback":           is_fallback,
    }


def _etherscan_is_pro_only(data: dict) -> bool:
    if data.get("status") in ("1", 1):
        return False
    text = f"{data.get('message', '')} {data.get('result', '')}".lower()
    return "api pro" in text or "upgrade to api pro" in text


def _parse_tokeninfo_result(data: dict) -> tuple[int | None, dict | None]:
    """Extrae holdersCount y campos útiles del endpoint tokeninfo."""
    result = data.get("result")
    row: dict | None = None
    if isinstance(result, list) and result:
        row = result[0] if isinstance(result[0], dict) else None
    elif isinstance(result, dict):
        row = result

    if not row:
        return None, None

    holders = row.get("holdersCount")
    holder_count = int(holders) if holders is not None else None

    extra = {
        k: row[k]
        for k in ("tokenName", "symbol", "website", "description", "tokenType", "totalSupply")
        if row.get(k)
    }
    return holder_count, extra or None


async def _fetch_blockscout_holders(
    contract_address: str,
    network: str,
) -> tuple[int | None, dict | None, str | None]:
    """Holders vía Blockscout API v2 (sin API key)."""
    base = _BLOCKSCOUT_API.get(network)
    if not base:
        return None, None, f"Blockscout no configurado para {network}"

    url = f"{base}/api/v2/tokens/{contract_address}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers={"accept": "application/json"})
        if r.status_code == 404:
            return None, None, "Token no indexado en Blockscout para esta red"
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        return None, None, f"Blockscout error: {exc}"

    raw = data.get("holders_count")
    holders: int | None = None
    if raw is not None:
        try:
            holders = int(raw)
        except (TypeError, ValueError):
            pass

    extra = {
        k: data[k]
        for k in ("name", "symbol", "type", "total_supply")
        if data.get(k) is not None
    }
    if not holders and not extra:
        return None, None, "Blockscout no devolvió holders_count"
    return holders, extra or None, None


async def _fetch_etherscan_tokeninfo(
    contract_address: str,
    network: str,
) -> tuple[int | None, dict | None, str | None, bool]:
    """
    Etherscan tokeninfo (API Pro para holders).
    Returns (holders, extra, warning, pro_only_blocked).
    """
    cfg = _NETWORKS[network]
    api_key, use_v2 = _explorer_api_key(network)
    if not api_key:
        return None, None, None, False

    params: dict[str, str] = {
        "module":          "token",
        "action":          "tokeninfo",
        "contractaddress": contract_address,
        "apikey":          api_key,
    }
    base_url = _ETHERSCAN_V2_API if use_v2 else cfg["explorer_api"]
    if use_v2:
        params["chainid"] = str(cfg["chain_id"])

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(base_url, params=params)
        data = r.json()
    except Exception as exc:
        return None, None, f"Etherscan error: {exc}", False

    if _etherscan_is_pro_only(data):
        logger.info("etherscan_tokeninfo_pro_only", network=network, contract=contract_address)
        return None, None, None, True

    if data.get("status") not in ("1", 1):
        msg = data.get("message") or data.get("result") or "explorer error"
        return None, None, f"Etherscan: {msg}", False

    holders, extra = _parse_tokeninfo_result(data)
    if holders is None and not extra:
        return None, None, "holdersCount not in Etherscan tokeninfo", False
    return holders, extra, None, False


async def _fetch_holder_count_and_extra(
    contract_address: str,
    network: str,
) -> tuple[int | None, dict | None, list[str]]:
    """
    Obtiene holders + metadata de explorer.
    Etherscan tokeninfo/holders = API Pro → fallback Blockscout (gratis).
    """
    notes: list[str] = []
    api_key, _ = _explorer_api_key(network)

    holders: int | None = None
    extra: dict | None = None

    if api_key:
        holders, extra, warn, pro_only = await _fetch_etherscan_tokeninfo(
            contract_address, network,
        )
        if warn and not pro_only:
            notes.append(warn)
        if pro_only:
            notes.append(
                "Etherscan tokeninfo requiere API Pro; usando Blockscout para holders."
            )
    else:
        notes.append(
            f"Sin {_explorer_env_label(network)}; intentando Blockscout para holders."
        )

    if holders is None:
        bs_holders, bs_extra, bs_warn = await _fetch_blockscout_holders(
            contract_address, network,
        )
        if bs_holders is not None:
            holders = bs_holders
            extra = {**(extra or {}), **(bs_extra or {}), "source": "blockscout"}
            logger.info(
                "blockscout_holders_ok",
                network=network,
                contract=contract_address,
                holders=holders,
            )
        elif bs_warn:
            notes.append(bs_warn)

    return holders, extra, notes


async def fetch_token_metadata(contract_address: str, network: str = "ethereum") -> dict:
    """
    Fetch ERC-20 metadata from the blockchain.

    Retries 3 times on connection failure.
    Never raises — returns {'error': '...'} on total failure.
    """
    if network not in _NETWORKS:
        return {"error": f"Unsupported network '{network}'. Supported: {list(_NETWORKS)}"}

    short = (contract_address[:10] + "…") if len(contract_address) > 10 else contract_address
    trace_emit(
        "rpc",
        "technical_token_analysis",
        f"→ JSON-RPC ({network}) · ERC-20 name/symbol/decimals/totalSupply · {short}",
    )

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            metadata = await asyncio.to_thread(_fetch_erc20_sync, contract_address, network)
            break
        except Exception as exc:
            last_err = exc
            logger.warning("rpc_attempt_failed", attempt=attempt + 1, network=network, error=str(exc))
    else:
        logger.error("rpc_all_attempts_failed", contract=contract_address, network=network, error=str(last_err))
        trace_emit(
            "rpc",
            "technical_token_analysis",
            f"← JSON-RPC falló tras 3 intentos · {last_err!s}"[:180],
        )
        return {"error": f"RPC failed after 3 attempts: {last_err}"}

    sym = metadata.get("token_symbol", "?")
    trace_emit(
        "rpc",
        "technical_token_analysis",
        f"← JSON-RPC OK · {sym} · supply {metadata.get('total_supply_formatted', '?')}",
    )

    api_key, use_v2 = _explorer_api_key(network)
    bs_base = _BLOCKSCOUT_API.get(network, "")
    if api_key:
        explorer_url = _ETHERSCAN_V2_API if use_v2 else _NETWORKS[network]["explorer_api"]
        trace_emit(
            "web",
            "technical_token_analysis",
            f"→ HTTPS {explorer_url} · tokeninfo"
            + (f" · chainid={_NETWORKS[network]['chain_id']}" if use_v2 else "")
            + (f" · fallback {bs_base}" if bs_base else ""),
        )
    elif bs_base:
        trace_emit(
            "web",
            "technical_token_analysis",
            f"→ HTTPS {bs_base}/api/v2/tokens/… · holders (Blockscout)",
        )
    else:
        trace_emit(
            "web",
            "technical_token_analysis",
            "— Sin explorer configurado · holders no disponibles",
        )

    holder_count, explorer_extra, holder_notes = await _fetch_holder_count_and_extra(
        contract_address, network,
    )
    if holder_count is not None:
        source = (explorer_extra or {}).get("source", "etherscan")
        trace_emit(
            "web",
            "technical_token_analysis",
            f"← Holders OK ({source}) · ≈ {holder_count:,}",
        )
    elif api_key or bs_base:
        trace_emit(
            "web",
            "technical_token_analysis",
            "← Holders no disponibles en explorer",
        )

    metadata["holder_count"] = holder_count
    if explorer_extra:
        metadata["explorer"] = explorer_extra

    warnings: list[str] = []
    for note in holder_notes:
        if holder_count is None:
            warnings.append(note)
        elif "API Pro" in note:
            metadata["explorer_note"] = note
    metadata["warnings"] = warnings

    logger.info(
        "rpc_success",
        network=network,
        contract=contract_address,
        symbol=metadata.get("token_symbol"),
        holders=holder_count,
        fallback=metadata.get("rpc_fallback"),
    )
    return metadata
