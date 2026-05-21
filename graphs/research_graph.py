import re
from typing import Literal, NotRequired, TypedDict

import structlog
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from config.settings import settings
from models.schemas import ClassifyOutput, CryptoAnalysis, FreeCryptoAnalysis
from tools.web_search import search_crypto

logger = structlog.get_logger()

# ── Query parsing helpers ──────────────────────────────────────────────────────

_CONTRACT_RE = re.compile(r'\b(0x[0-9a-fA-F]{40})\b')

_NETWORK_KEYWORDS: dict[str, str] = {
    "ethereum": "ethereum",
    "eth":      "ethereum",
    "base":     "base",
    "polygon":  "polygon",
    "matic":    "polygon",
    "arbitrum": "arbitrum",
    "arb":      "arbitrum",
}


def _extract_contract(text: str) -> str | None:
    m = _CONTRACT_RE.search(text)
    return m.group(1) if m else None


def _extract_network(text: str) -> str | None:
    lower = text.lower()
    for keyword, network in _NETWORK_KEYWORDS.items():
        if re.search(rf'\b{keyword}\b', lower):
            return network
    return None


# ── State ─────────────────────────────────────────────────────────────────────

class ResearchState(TypedDict):
    # Core pipeline fields
    query:          str
    token_name:     str
    classification: str
    search_results: list[dict]
    sources:        list[str]
    raw_content:    str
    analysis:       dict | None
    error:          str | None
    # Technical analysis fields (populated by classify + technical_token_analysis)
    contract_address:            NotRequired[str | None]
    network:                     NotRequired[str]
    technical_analysis_required: NotRequired[bool]
    token_metadata:              NotRequired[dict | None]
    technical_warnings:          NotRequired[list[str]]
    # Per-request model override
    model:                       NotRequired[str]
    # free | premium — controls graph routing and analyze depth
    analysis_depth:              NotRequired[Literal["free", "premium"]]
    # x402 — set by API after facilitator verify (premium only)
    payment_verified:            NotRequired[bool]
    payment_summary:             NotRequired[dict[str, str]]


# ── LLM factory ───────────────────────────────────────────────────────────────

def _llm(model: str | None = None) -> ChatOpenAI:
    return ChatOpenAI(
        model=model or settings.model_name,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.1,
    )


# ── Node: payment (premium) ───────────────────────────────────────────────────

async def payment_node(state: ResearchState) -> dict:
    """Records verified x402 payment before research nodes run."""
    if state.get("analysis_depth", "premium") == "free":
        return {}

    if not state.get("payment_verified"):
        logger.error("payment_not_verified")
        return {"error": "Premium research requires verified x402 payment"}

    summary = state.get("payment_summary") or {}
    logger.info(
        "payment_gate_passed",
        payer=summary.get("payer"),
        amount=summary.get("amount"),
        network=summary.get("network"),
    )
    return {}


# ── Node: classify ────────────────────────────────────────────────────────────

_CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "Extract cryptocurrency research intent from the user query.\n\n"
        "Fields to extract:\n"
        "- token_name: token name or symbol (e.g. 'DEXTF', 'Bitcoin', 'ETH')\n"
        "- classification: one of token_analysis | price_prediction | fundamentals | sentiment\n"
        "- contract_address: 0x-prefixed contract address if present, else null\n"
        "- network: blockchain network if mentioned (ethereum/base/polygon/arbitrum), default 'ethereum'\n"
        "- technical_analysis_required: true if the user asks for contract/on-chain/technical analysis\n",
    ),
    ("human", "{query}"),
])


async def classify_node(state: ResearchState) -> dict:
    try:
        chain   = _CLASSIFY_PROMPT | _llm(state.get("model")).with_structured_output(ClassifyOutput)
        result: ClassifyOutput = await chain.ainvoke({"query": state["query"]})

        # Regex fallbacks — LLMs sometimes miss the address even when it's explicit in the query
        query            = state["query"]
        contract_address = result.contract_address or _extract_contract(query)
        network          = result.network or _extract_network(query) or "ethereum"

        # If a contract address is present, technical analysis is always required
        technical = result.technical_analysis_required or bool(contract_address)

        logger.info(
            "classified",
            token=result.token_name,
            type=result.classification,
            contract=contract_address,
            network=network,
            technical=technical,
            llm_contract=result.contract_address,   # log whether LLM found it or regex did
        )
        return {
            "token_name":                 result.token_name,
            "classification":             result.classification,
            "contract_address":           contract_address,
            "network":                    network,
            "technical_analysis_required": technical,
        }
    except Exception as exc:
        logger.error("classify_failed", error=str(exc))
        return {"error": f"Classification failed: {exc}"}


# ── Node: search ──────────────────────────────────────────────────────────────

async def search_node(state: ResearchState) -> dict:
    try:
        contract = state.get("contract_address")
        network  = state.get("network", "ethereum")
        context  = state["classification"]
        if contract:
            context = f"{context} contract:{contract} network:{network}"

        results = await search_crypto(token_name=state["token_name"], context=context)
        return {"search_results": results}
    except Exception as exc:
        logger.error("search_failed", error=str(exc))
        return {"error": f"Search failed: {exc}"}


# ── Node: technical_token_analysis ────────────────────────────────────────────

async def technical_token_analysis_node(state: ResearchState) -> dict:
    from tools.token_rpc import fetch_token_metadata

    contract_address = state.get("contract_address")
    network          = state.get("network", "ethereum")

    if not contract_address:
        return {"technical_warnings": ["technical_token_analysis: no contract address in state"]}

    logger.info("technical_analysis_start", contract=contract_address, network=network)
    metadata = await fetch_token_metadata(contract_address, network)

    if metadata.get("error"):
        logger.warning("technical_analysis_failed", error=metadata["error"])
        return {
            "token_metadata":    None,
            "technical_warnings": [metadata["error"]],
        }

    warnings = metadata.pop("warnings", [])
    # Remove internal-only fields before storing in state
    metadata.pop("rpc_url",      None)
    metadata.pop("rpc_fallback", None)

    logger.info(
        "technical_analysis_done",
        symbol=metadata.get("token_symbol"),
        supply=metadata.get("total_supply_formatted"),
    )
    return {
        "token_metadata":    metadata,
        "technical_warnings": warnings,
    }


# ── Node: aggregate ───────────────────────────────────────────────────────────

def aggregate_node(state: ResearchState) -> dict:
    sources: list[str] = []
    parts:   list[str] = []
    for result in state.get("search_results", []):
        if not isinstance(result, dict):
            continue
        if url := result.get("url"):
            sources.append(url)
        if content := result.get("content"):
            parts.append(content)
    return {
        "sources":     sources,
        "raw_content": "\n\n---\n\n".join(parts),
    }


# ── Node: analyze ─────────────────────────────────────────────────────────────

def _content_from_search(state: ResearchState) -> str:
    """Build research text from search_results when aggregate was skipped (free path)."""
    parts: list[str] = []
    for result in state.get("search_results", []):
        if isinstance(result, dict) and (content := result.get("content")):
            parts.append(content)
    return "\n\n---\n\n".join(parts)


_FREE_ANALYZE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a cryptocurrency research analyst. Produce a SHORT free-tier snapshot only. "
        "Base claims on the supplied content. "
        "Summary: one concise paragraph. "
        "Provide exactly 2-3 bullish points and 2-3 bearish points (no risks section). "
        "Confidence score: 0.0 = very uncertain, 1.0 = very confident.",
    ),
    (
        "human",
        "Token: {token_name}\n"
        "Original query: {query}\n\n"
        "Research content:\n{raw_content}\n\n"
        "Generate the short free report.",
    ),
])

_ANALYZE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a professional cryptocurrency research analyst. "
        "Analyze the provided research content and generate an objective, data-driven report. "
        "Base every claim on the supplied content. "
        "Confidence score: 0.0 = very uncertain (sparse/conflicting data), "
        "1.0 = very confident (rich, consistent data). "
        "Provide 3–5 items each for bullish points, bearish points, and risks.",
    ),
    (
        "human",
        "Token: {token_name}\n"
        "Original query: {query}\n\n"
        "{technical_context}"
        "Research content:\n{raw_content}\n\n"
        "Generate the analysis report.",
    ),
])


def _build_technical_context(state: ResearchState) -> str:
    metadata = state.get("token_metadata")
    if not metadata or metadata.get("error"):
        return ""
    lines = [
        "On-chain technical data:",
        f"- Network: {metadata.get('network')} (Chain ID: {metadata.get('chain_id')})",
        f"- Contract: {metadata.get('contract_address')}",
        f"- Symbol: {metadata.get('token_symbol')}",
        f"- Decimals: {metadata.get('decimals')}",
        f"- Total Supply: {metadata.get('total_supply_formatted')}",
    ]
    if metadata.get("holder_count") is not None:
        lines.append(f"- Holders: {metadata['holder_count']:,}")
    return "\n".join(lines) + "\n\n"


async def analyze_node(state: ResearchState) -> dict:
    try:
        depth = state.get("analysis_depth", "premium")
        raw = state.get("raw_content") or _content_from_search(state)
        raw = raw[:8000]

        if depth == "free":
            chain = _FREE_ANALYZE_PROMPT | _llm(state.get("model")).with_structured_output(FreeCryptoAnalysis)
            result: FreeCryptoAnalysis = await chain.ainvoke({
                "token_name": state["token_name"],
                "query":      state["query"],
                "raw_content": raw,
            })
            analysis = {
                **result.model_dump(),
                "risks": [],
            }
        else:
            chain = _ANALYZE_PROMPT | _llm(state.get("model")).with_structured_output(CryptoAnalysis)
            full: CryptoAnalysis = await chain.ainvoke({
                "token_name":        state["token_name"],
                "query":             state["query"],
                "raw_content":       raw,
                "technical_context": _build_technical_context(state),
            })
            analysis = full.model_dump()

        logger.info(
            "analysis_complete",
            token=analysis.get("token"),
            confidence=analysis.get("confidence_score"),
            depth=depth,
        )
        return {"analysis": analysis}
    except Exception as exc:
        logger.error("analyze_failed", error=str(exc))
        return {"error": f"Analysis failed: {exc}"}


# ── Graph assembly ────────────────────────────────────────────────────────────

def _stop_on_error(next_node: str):
    """Proceed to next_node unless an error is set in state."""
    def _route(state: ResearchState) -> str:
        return END if state.get("error") else next_node
    return _route


def _route_after_search(state: ResearchState) -> str:
    """Free: search → analyze. Premium: search → technical → aggregate → analyze."""
    if state.get("error"):
        return END
    if state.get("analysis_depth", "premium") == "free":
        return "analyze"
    return "technical_token_analysis"


def _route_from_start(state: ResearchState) -> str:
    if state.get("error"):
        return END
    if state.get("analysis_depth", "premium") == "free":
        return "classify"
    return "payment"


def build_research_graph():
    graph = StateGraph(ResearchState)

    graph.add_node("payment",                  payment_node)
    graph.add_node("classify",                 classify_node)
    graph.add_node("search",                   search_node)
    graph.add_node("technical_token_analysis", technical_token_analysis_node)
    graph.add_node("aggregate",                aggregate_node)
    graph.add_node("analyze",                  analyze_node)

    graph.add_conditional_edges(
        START,
        _route_from_start,
        {"payment": "payment", "classify": "classify", END: END},
    )
    graph.add_conditional_edges(
        "payment",
        _stop_on_error("classify"),
        {"classify": "classify", END: END},
    )
    graph.add_conditional_edges(
        "classify",
        _stop_on_error("search"),
        {"search": "search", END: END},
    )
    graph.add_conditional_edges(
        "search",
        _route_after_search,
        {
            "analyze":                  "analyze",
            "technical_token_analysis": "technical_token_analysis",
            END:                        END,
        },
    )
    graph.add_conditional_edges(
        "technical_token_analysis",
        _stop_on_error("aggregate"),
        {"aggregate": "aggregate", END: END},
    )
    graph.add_conditional_edges(
        "aggregate",
        _stop_on_error("analyze"),
        {"analyze": "analyze", END: END},
    )
    graph.add_edge("analyze", END)

    return graph.compile()
