import time
from typing import AsyncIterator
from urllib.parse import urlparse

import structlog

from config.stream_trace import trace_drain, trace_reset
from graphs.research_graph import ResearchState, build_research_graph
from models.schemas import CryptoReport, ResearchResponse, TechnicalDetails

logger = structlog.get_logger()

_NODE_LABELS: dict[str, str] = {
    "payment":                   "x402 payment gate",
    "classify":                  "Classifying request",
    "search":                    "Searching the web",
    "technical_token_analysis":  "Fetching on-chain data",
    "aggregate":                 "Aggregating content",
    "analyze":                   "Generating analysis",
}


def _hostname(url: str) -> str:
    try:
        return urlparse(url).hostname or url
    except Exception:
        return url[:30]


def _step_detail(node: str, output: dict) -> str:
    """Human-readable summary of what a node produced."""
    if node == "payment":
        return "Payment verified — starting research"

    if node == "classify":
        token = output.get("token_name", "")
        cls   = output.get("classification", "").replace("_", " ")
        parts = [f"{token} — {cls}"] if token else []
        if output.get("contract_address"):
            net = output.get("network", "ethereum")
            parts.append(f"contract on {net}")
        return "  ·  ".join(parts)

    if node == "search":
        n = len(output.get("search_results", []))
        return f"{n} source{'s' if n != 1 else ''} found"

    if node == "aggregate":
        sources  = output.get("sources", [])
        chars    = len(output.get("raw_content", ""))
        hosts    = [_hostname(u) for u in sources[:3]]
        extra    = f" +{len(sources) - 3}" if len(sources) > 3 else ""
        host_str = ", ".join(hosts) + extra
        return f"{host_str} · {chars:,} chars" if host_str else f"{chars:,} chars"

    if node == "analyze":
        conf = (output.get("analysis") or {}).get("confidence_score", 0)
        return f"Confidence {conf:.0%}"

    if node == "technical_token_analysis":
        metadata = output.get("token_metadata")
        if not metadata or metadata.get("error"):
            warnings = output.get("technical_warnings", [])
            return warnings[0][:70] if warnings else "no data fetched"
        return (
            f"{metadata.get('token_symbol')} · "
            f"{metadata.get('total_supply_formatted')} supply · "
            f"{metadata.get('network')}"
        )

    return ""


def _state_hint_start(node: str, input_data) -> str:
    """Brief hint about what the node is receiving as input."""
    if not isinstance(input_data, dict):
        return ""
    if node == "payment":
        summary = input_data.get("payment_summary") or {}
        payer = summary.get("payer", "?")
        amt   = summary.get("amount", "?")
        return f" · payer={payer[:10]}… amount={amt} atomic"
    if node == "classify":
        q   = input_data.get("query", "")
        end = "…" if len(q) > 60 else ""
        return f' · query: "{q[:60]}{end}"'
    if node == "search":
        return (f' · token={input_data.get("token_name", "?")} '
                f'class={input_data.get("classification", "?")}')
    if node == "aggregate":
        n = len(input_data.get("search_results", []))
        return f" · {n} search result{'s' if n != 1 else ''} to process"
    if node == "analyze":
        chars = len(input_data.get("raw_content", ""))
        return f" · {chars:,} chars of content"
    if node == "technical_token_analysis":
        contract = input_data.get("contract_address") or "?"
        network  = input_data.get("network", "ethereum")
        short    = (contract[:10] + "…") if len(contract) > 10 else contract
        return f" · {short} on {network}"
    return ""


def _state_hint_end(node: str, output: dict) -> str:
    """Brief hint about what the node produced."""
    if node == "payment":
        return "verified"
    if node == "classify":
        t = output.get("token_name", "?")
        c = output.get("classification", "?").replace("_", " ")
        return f"token={t} type={c}"
    if node == "search":
        n = len(output.get("search_results", []))
        return f"{n} result{'s' if n != 1 else ''} fetched"
    if node == "aggregate":
        sources = output.get("sources", [])
        chars   = len(output.get("raw_content", ""))
        return f"{len(sources)} sources · {chars:,} chars"
    if node == "analyze":
        conf = (output.get("analysis") or {}).get("confidence_score", 0)
        return f"confidence={conf:.0%}"
    if node == "technical_token_analysis":
        metadata = output.get("token_metadata")
        if metadata and not metadata.get("error"):
            return f"symbol={metadata.get('token_symbol')} decimals={metadata.get('decimals')}"
        warnings = output.get("technical_warnings", [])
        return warnings[0][:60] if warnings else "no data"
    return ""


def _build_report(query: str, final: dict, *, mode: str) -> CryptoReport:
    analysis = final["analysis"]
    if mode == "free":
        return CryptoReport(
            token=analysis["token"],
            summary=analysis["summary"],
            bullish_points=analysis["bullish_points"],
            bearish_points=analysis["bearish_points"],
            risks=[],
            confidence_score=analysis["confidence_score"],
            mode="free",
            sources=[],
            query=query,
            technical_details=None,
        )
    return CryptoReport(
        **analysis,
        mode="premium",
        sources=final.get("sources", []),
        query=query,
        technical_details=_build_technical_details(final),
    )


def _build_technical_details(accumulated: dict) -> TechnicalDetails | None:
    metadata = accumulated.get("token_metadata")
    if not metadata or metadata.get("error"):
        return None
    try:
        return TechnicalDetails(
            network=               metadata["network"],
            chain_id=              metadata["chain_id"],
            contract_address=      metadata["contract_address"],
            token_name=            metadata["token_name"],
            token_symbol=          metadata["token_symbol"],
            decimals=              metadata["decimals"],
            total_supply_raw=      metadata["total_supply_raw"],
            total_supply_formatted=metadata["total_supply_formatted"],
            holder_count=          metadata.get("holder_count"),
            warnings=              accumulated.get("technical_warnings", []),
        )
    except Exception as exc:
        logger.warning("technical_details_build_failed", error=str(exc))
        return None


class CryptoResearchAgent:
    """Orchestrates the LangGraph research pipeline."""

    def __init__(self) -> None:
        self._graph = build_research_graph()

    def _initial_state(
        self,
        query: str,
        model: str | None = None,
        *,
        analysis_depth: str = "free",
        payment_verified: bool = False,
        payment_summary: dict[str, str] | None = None,
    ) -> ResearchState:
        from config.settings import settings as _settings
        return {
            "query":                      query,
            "token_name":                 "",
            "classification":             "",
            "search_results":             [],
            "sources":                    [],
            "raw_content":                "",
            "analysis":                   None,
            "error":                      None,
            "contract_address":           None,
            "network":                    "ethereum",
            "technical_analysis_required": False,
            "token_metadata":             None,
            "technical_warnings":         [],
            "model":                      model or _settings.model_name,
            "analysis_depth":             analysis_depth,
            "payment_verified":           payment_verified,
            "payment_summary":            payment_summary or {},
        }

    # ── Batch (non-streaming) ─────────────────────────────────────────────────

    async def research(
        self,
        query: str,
        model: str | None = None,
        *,
        mode: str = "free",
        payment_verified: bool = False,
        payment_summary: dict[str, str] | None = None,
    ) -> ResearchResponse:
        start = time.monotonic()
        depth = "premium" if mode == "premium" else "free"
        logger.info("research_start", query=query, model=model, mode=mode)
        try:
            final   = await self._graph.ainvoke(
                self._initial_state(
                    query,
                    model,
                    analysis_depth=depth,
                    payment_verified=payment_verified,
                    payment_summary=payment_summary,
                ),
            )
            elapsed = int((time.monotonic() - start) * 1000)

            if final.get("error"):
                return ResearchResponse(success=False, error=final["error"], processing_time_ms=elapsed)
            if not final.get("analysis"):
                return ResearchResponse(success=False, error="Analysis was not generated", processing_time_ms=elapsed)

            report = _build_report(query, final, mode=mode)
            logger.info("research_complete", token=report.token, confidence=report.confidence_score, elapsed_ms=elapsed)
            return ResearchResponse(success=True, report=report, processing_time_ms=elapsed)

        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.error("research_error", query=query, error=str(exc))
            return ResearchResponse(success=False, error=str(exc), processing_time_ms=elapsed)

    # ── Streaming ─────────────────────────────────────────────────────────────

    async def astream_research(
        self,
        query: str,
        model: str | None = None,
        *,
        mode: str = "free",
        payment_verified: bool = False,
        payment_summary: dict[str, str] | None = None,
    ) -> AsyncIterator[dict]:
        """
        Async generator that yields SSE-compatible dicts.

        Event types:
          step_start  — a graph node began         {node, label}
          step_end    — a node finished             {node, label, detail}
          step_skip   — a node was routed around    {node, label, detail}
          step_error  — a node hit an error         {node, label, detail}
          log         — execution trace entry       {level, node, message}
                        level ∈ {langchain, langgraph, agent, web, rpc}
          result      — final ResearchResponse JSON {data: {...}}
          error       — top-level failure           {message}
        """
        depth = "premium" if mode == "premium" else "free"
        logger.info("stream_start", query=query, model=model, mode=mode)
        trace_reset()
        accumulated: dict = {}
        started:     set  = set()
        ended:       set  = set()

        try:
            async for event in self._graph.astream_events(
                self._initial_state(
                    query,
                    model,
                    analysis_depth=depth,
                    payment_verified=payment_verified,
                    payment_summary=payment_summary,
                ),
                version="v2",
            ):
                for te in trace_drain():
                    yield te

                ev   = event.get("event", "")
                meta = event.get("metadata", {})
                node = meta.get("langgraph_node", "")
                name = event.get("name", "LLM")

                # ── LangChain: LLM call events (checked before node filter) ──
                if ev == "on_chat_model_start" and node in _NODE_LABELS:
                    yield {
                        "type":    "log",
                        "level":   "langchain",
                        "node":    node,
                        "message": f"→ {name} · preparing request",
                    }
                    continue

                if ev == "on_chat_model_end" and node in _NODE_LABELS:
                    output = event.get("data", {}).get("output")
                    tokens = ""
                    if output is not None:
                        usage = getattr(output, "usage_metadata", None)
                        if isinstance(usage, dict):
                            inp    = usage.get("input_tokens", "?")
                            out    = usage.get("output_tokens", "?")
                            tokens = f" · {inp}↑ {out}↓ tokens"
                    yield {
                        "type":    "log",
                        "level":   "langchain",
                        "node":    node,
                        "message": f"← {name} responded{tokens}",
                    }
                    continue

                if not node or node not in _NODE_LABELS:
                    continue

                # ── LangGraph: node lifecycle ─────────────────────────────────
                if ev == "on_chain_start" and node not in started:
                    started.add(node)
                    yield {"type": "step_start", "node": node, "label": _NODE_LABELS[node]}
                    hint = _state_hint_start(node, event.get("data", {}).get("input"))
                    yield {
                        "type":    "log",
                        "level":   "langgraph",
                        "node":    node,
                        "message": f"node:{node} started{hint}",
                    }

                elif ev == "on_chain_end" and node not in ended:
                    raw = event.get("data", {}).get("output")

                    # astream_events fires on_chain_end for every inner
                    # LangChain chain inside the node (e.g. the structured-
                    # output chain), all sharing the same langgraph_node tag.
                    # Node functions always return plain dicts; skip anything
                    # else so we only react to the actual node-level result.
                    if not isinstance(raw, dict):
                        continue

                    ended.add(node)
                    output = raw
                    accumulated.update(output)

                    if output.get("error"):
                        for te in trace_drain():
                            yield te
                        yield {
                            "type":   "step_error",
                            "node":   node,
                            "label":  _NODE_LABELS[node],
                            "detail": output["error"],
                        }
                        yield {
                            "type":    "log",
                            "level":   "langgraph",
                            "node":    node,
                            "message": f"node:{node} error → {output['error'][:100]}",
                        }
                        break

                    detail = _step_detail(node, output)
                    yield {
                        "type":   "step_end",
                        "node":   node,
                        "label":  _NODE_LABELS[node],
                        "detail": detail,
                    }
                    yield {
                        "type":    "log",
                        "level":   "langgraph",
                        "node":    node,
                        "message": f"node:{node} done → {_state_hint_end(node, output)}",
                    }
                    if detail:
                        yield {
                            "type":    "log",
                            "level":   "agent",
                            "node":    node,
                            "message": detail,
                        }

                    # After search: emit skip events for nodes not run on this path
                    if node == "search" and depth == "free":
                        for skipped in ("technical_token_analysis", "aggregate"):
                            yield {
                                "type":   "step_skip",
                                "node":   skipped,
                                "label":  _NODE_LABELS[skipped],
                                "detail": "skipped — free tier",
                            }

        except Exception as exc:
            logger.error("stream_error", query=query, error=str(exc))
            for te in trace_drain():
                yield te
            yield {"type": "error", "message": str(exc)}
            return

        # ── Emit final result ─────────────────────────────────────────────────
        for te in trace_drain():
            yield te
        if accumulated.get("error"):
            yield {"type": "error", "message": accumulated["error"]}
        elif accumulated.get("analysis"):
            report   = _build_report(query, accumulated, mode=mode)
            response = ResearchResponse(success=True, report=report, processing_time_ms=0)
            yield {"type": "result", "data": response.model_dump(mode="json")}
        else:
            yield {"type": "error", "message": "Analysis could not be generated"}
