"""CoinGecko market-data helper — no API key required for basic endpoints."""

from typing import Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()

_COINGECKO_BASE = "https://api.coingecko.com/api/v3"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=False,
)
async def get_token_market_data(token_id: str) -> Optional[dict]:
    """
    Fetch basic market data from CoinGecko.

    token_id is the CoinGecko slug, e.g. 'bitcoin', 'ethereum', 'dextf'.
    Returns None if the token is not found or the request fails.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{_COINGECKO_BASE}/coins/{token_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "false",
                    "developer_data": "false",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            md = data.get("market_data", {})
            return {
                "name": data.get("name"),
                "symbol": data.get("symbol"),
                "current_price_usd": md.get("current_price", {}).get("usd"),
                "market_cap_usd": md.get("market_cap", {}).get("usd"),
                "price_change_24h_pct": md.get("price_change_percentage_24h"),
                "price_change_7d_pct": md.get("price_change_percentage_7d"),
                "total_volume_usd": md.get("total_volume", {}).get("usd"),
                "ath_usd": md.get("ath", {}).get("usd"),
                "atl_usd": md.get("atl", {}).get("usd"),
            }
        except Exception as exc:
            logger.warning("coingecko_failed", token_id=token_id, error=str(exc))
            return None
