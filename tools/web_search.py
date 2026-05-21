"""
Web search via Tavily (https://tavily.com).

If TAVILY_API_KEY is unset, falls back to mock_search for local / CI without a key.
"""

import asyncio

import structlog
from tavily import TavilyClient

from config.settings import settings
from config.stream_trace import trace_emit

logger = structlog.get_logger()

_DEFAULT_SEARCH_DEPTH = "basic"


def _build_query(token_name: str, context: str) -> str:
    parts = [token_name.strip(), "cryptocurrency", "crypto token"]
    ctx = (context or "").strip()
    if ctx:
        parts.append(ctx)
    return " ".join(p for p in parts if p)


async def search_crypto(token_name: str, context: str = "") -> list[dict]:
    """
    Return search hits as {url, content} dicts (same shape as mock_search).

    Uses settings.max_search_results and TAVILY_API_KEY from the environment.
    """
    if not (settings.tavily_api_key or "").strip():
        from tools.mock_search import search_crypto as mock_search

        logger.warning("tavily_skipped_no_api_key", fallback="mock_search")
        trace_emit(
            "web",
            "search",
            "→ Búsqueda mock (sin TAVILY_API_KEY) — no hay llamadas HTTP a Tavily",
        )
        results = await mock_search(token_name, context)
        trace_emit(
            "web",
            "search",
            f"← Mock · {len(results)} resultados locales",
        )
        return results

    query = _build_query(token_name, context)
    client = TavilyClient(api_key=settings.tavily_api_key)
    q_preview = query if len(query) <= 140 else query[:137] + "…"
    trace_emit(
        "web",
        "search",
        "→ Tavily HTTPS api.tavily.com/search "
        f"· max_results={settings.max_search_results} · query: {q_preview}",
    )

    def _run() -> dict:
        return client.search(
            query=query,
            max_results=settings.max_search_results,
            search_depth=_DEFAULT_SEARCH_DEPTH,
        )

    try:
        response = await asyncio.to_thread(_run)
    except Exception as exc:
        logger.error("tavily_search_failed", query=query, error=str(exc))
        trace_emit("web", "search", f"← Tavily error · {exc!s}"[:200])
        raise

    results: list[dict] = []
    for row in response.get("results") or []:
        if not isinstance(row, dict):
            continue
        url = (row.get("url") or "").strip()
        body = (row.get("content") or "").strip()
        title = (row.get("title") or "").strip()
        if title and body:
            body = f"{title}\n\n{body}"
        elif title and not body:
            body = title
        if url or body:
            results.append({"url": url, "content": body})

    logger.info(
        "tavily_search_ok",
        query=query,
        n=len(results),
    )
    trace_emit("web", "search", f"← Tavily OK · {len(results)} fuentes recibidas por HTTPS")
    return results if results else [{"url": "", "content": f"No Tavily results for: {query}"}]


__all__ = ["search_crypto"]
