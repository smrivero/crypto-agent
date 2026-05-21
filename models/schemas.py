from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ClassifyOutput(BaseModel):
    token_name: str = Field(description="Token name or symbol, e.g. 'DEXTF', 'Bitcoin', 'ETH'")
    classification: Literal["token_analysis", "price_prediction", "fundamentals", "sentiment"] = Field(
        description="Type of research requested"
    )
    contract_address: Optional[str] = Field(
        default=None,
        description="ERC-20 contract address if present in the query (0x-prefixed hex string), else null",
    )
    network: Literal["ethereum", "base", "polygon", "arbitrum"] = Field(
        default="ethereum",
        description="Blockchain network mentioned in the query. Default to 'ethereum' if not specified.",
    )
    technical_analysis_required: bool = Field(
        default=False,
        description="True if the user explicitly asks for contract, on-chain, or technical analysis",
    )


class CryptoAnalysis(BaseModel):
    """Structured output produced by the LLM analysis node."""

    token: str = Field(description="Token name or symbol")
    summary: str = Field(description="Comprehensive 2-3 paragraph summary of the token")
    bullish_points: list[str] = Field(description="3-5 positive factors and bullish signals")
    bearish_points: list[str] = Field(description="3-5 negative factors and bearish signals")
    risks: list[str] = Field(description="3-5 key risks investors should be aware of")
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Analysis confidence based on data quality and consistency (0.0–1.0)",
    )


class TechnicalDetails(BaseModel):
    """On-chain ERC-20 metadata fetched directly from the blockchain."""

    network: str
    chain_id: int
    contract_address: str
    token_name: str
    token_symbol: str
    decimals: int
    total_supply_raw: str
    total_supply_formatted: str
    holder_count: Optional[int] = None
    warnings: list[str] = Field(default_factory=list)


class FreeCryptoAnalysis(BaseModel):
    """Short report for free tier."""

    token: str
    summary: str = Field(description="Brief 1-paragraph summary")
    bullish_points: list[str] = Field(description="Top 2-3 bullish signals")
    bearish_points: list[str] = Field(description="Top 2-3 bearish signals")
    confidence_score: float = Field(ge=0.0, le=1.0)


class CryptoReport(CryptoAnalysis):
    """Final report returned to callers — extends analysis with metadata."""

    mode: Literal["free", "premium"] = "premium"
    sources: list[str] = Field(default_factory=list, description="Source URLs used")
    query: str = Field(description="Original research query")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    technical_details: Optional[TechnicalDetails] = None


class ResearchRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=3,
        description="Research query, e.g. 'Analyze DEXTF token'",
    )
    mode: Literal["free", "premium"] = Field(
        default="free",
        description="free = short report; premium = full analysis (x402 payment required)",
    )
    model: str = Field(
        default="gpt-5.4-mini",
        description="OpenAI model to use for this request",
    )


class ResearchResponse(BaseModel):
    success: bool
    report: Optional[CryptoReport] = None
    error: Optional[str] = None
    processing_time_ms: int
