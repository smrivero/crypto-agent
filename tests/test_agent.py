from unittest.mock import AsyncMock, patch

import pytest

from agents.research_agent import CryptoResearchAgent
from models.schemas import ResearchResponse


_MOCK_ANALYSIS = {
    "token": "DEXTF",
    "summary": "DEXTF is a DeFi index token...",
    "bullish_points": ["Innovative index product", "Growing DeFi sector"],
    "bearish_points": ["Low liquidity", "Small market cap"],
    "risks": ["Smart contract risk", "Regulatory uncertainty"],
    "confidence_score": 0.72,
}

_MOCK_STATE = {
    "query": "Analyze DEXTF token",
    "token_name": "DEXTF",
    "classification": "token_analysis",
    "search_results": [],
    "sources": ["https://example.com/dextf"],
    "raw_content": "DEXTF content...",
    "analysis": _MOCK_ANALYSIS,
    "error": None,
}


@pytest.mark.asyncio
async def test_research_returns_report():
    with patch("agents.research_agent.build_research_graph") as mock_build:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = _MOCK_STATE
        mock_build.return_value = mock_graph

        agent = CryptoResearchAgent()
        response = await agent.research("Analyze DEXTF token", mode="premium")

    assert isinstance(response, ResearchResponse)
    assert response.success is True
    assert response.report is not None
    assert response.report.token == "DEXTF"
    assert 0.0 <= response.report.confidence_score <= 1.0
    assert len(response.report.bullish_points) > 0
    assert len(response.report.bearish_points) > 0
    assert len(response.report.risks) > 0
    assert response.processing_time_ms >= 0


@pytest.mark.asyncio
async def test_research_handles_graph_error():
    with patch("agents.research_agent.build_research_graph") as mock_build:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = RuntimeError("LLM timeout")
        mock_build.return_value = mock_graph

        agent = CryptoResearchAgent()
        response = await agent.research("Analyze DEXTF token", mode="premium")

    assert response.success is False
    assert response.report is None
    assert "LLM timeout" in (response.error or "")


@pytest.mark.asyncio
async def test_research_handles_node_error_in_state():
    error_state = {**_MOCK_STATE, "analysis": None, "error": "Search failed: 429"}
    with patch("agents.research_agent.build_research_graph") as mock_build:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = error_state
        mock_build.return_value = mock_graph

        agent = CryptoResearchAgent()
        response = await agent.research("Analyze DEXTF token", mode="premium")

    assert response.success is False
    assert "Search failed" in (response.error or "")
