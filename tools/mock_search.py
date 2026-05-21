"""
Deterministic mock search tool.

Replaces Tavily for local development and LangGraph learning.
No network calls, no API keys required.
Results are keyed by token name so the full graph pipeline
(classify → search → aggregate → analyze) behaves realistically.
"""

import structlog

logger = structlog.get_logger()

# ── Pre-seeded result database ────────────────────────────────────────────────

_RESULTS: dict[str, list[dict]] = {
    "bitcoin": [
        {
            "url": "https://mock.cryptonews/btc-funding-rates",
            "content": (
                "Bitcoin funding rates turned negative for the first time in three months, "
                "signaling exhaustion among leveraged longs. Analysts note this precedes "
                "short squeezes when spot demand remains intact."
            ),
        },
        {
            "url": "https://mock.etftracker/btc-inflows",
            "content": (
                "Spot Bitcoin ETF products recorded $512 M in net inflows last week, led by "
                "BlackRock's IBIT. Institutional demand continues to outpace new supply from miners."
            ),
        },
        {
            "url": "https://mock.derivatives/btc-open-interest",
            "content": (
                "Bitcoin open interest across major exchanges hit an all-time high of $35.2 B. "
                "Elevated OI combined with negative funding historically resolves in a sharp move."
            ),
        },
        {
            "url": "https://mock.chaindata/lightning-network",
            "content": (
                "Lightning Network capacity grew 40 % year-over-year, now holding 5,400 BTC. "
                "Merchant adoption via Lightning accelerated in Latin America and Southeast Asia."
            ),
        },
        {
            "url": "https://mock.macro/fed-rates-crypto",
            "content": (
                "Fed officials signal potential rate cuts in H2 2024, boosting risk assets. "
                "On-chain data shows long-term holders continue accumulating through volatility."
            ),
        },
    ],
    "ethereum": [
        {
            "url": "https://mock.ethresearch/dencun-impact",
            "content": (
                "Ethereum's Dencun upgrade (EIP-4844) cut Layer-2 transaction costs by up to 90 %, "
                "dramatically improving economics on Arbitrum, Optimism, and Base."
            ),
        },
        {
            "url": "https://mock.staking/eth-ratio",
            "content": (
                "Ethereum staking ratio reached 27 % of total supply with ~32 M ETH locked in the "
                "beacon chain. Lido and Rocket Pool dominate liquid staking."
            ),
        },
        {
            "url": "https://mock.defi/eth-tvl",
            "content": (
                "DeFi TVL on Ethereum surpassed $60 B post-bear-market recovery. "
                "Uniswap, Aave, and MakerDAO account for over 60 % of total Ethereum DeFi."
            ),
        },
        {
            "url": "https://mock.etfnews/eth-approval",
            "content": (
                "Spot Ethereum ETF approval probability rises as SEC engagement with issuers "
                "increases. Analysts estimate $5–10 B in inflows within six months of approval."
            ),
        },
        {
            "url": "https://mock.devmetrics/ethereum",
            "content": (
                "Ethereum leads all blockchains in developer activity with 4,000+ monthly active "
                "developers. EIP pipeline includes Pectra upgrade targeting validator UX improvements."
            ),
        },
    ],
    "dextf": [
        {
            "url": "https://mock.dextf/memento-zk-chain",
            "content": (
                "DEXTF, now rebranded Memento, launched a ZK-powered chain for institutional DeFi "
                "index products. The platform targets professional asset managers seeking structured "
                "on-chain exposure."
            ),
        },
        {
            "url": "https://mock.defiprotocols/atlas-upgrade",
            "content": (
                "The Atlas upgrade brings delta-neutral strategies and multi-asset weighted indices "
                "to the Memento mainnet. Early integrations with custody providers confirmed."
            ),
        },
        {
            "url": "https://mock.riskanalysis/dextf-tvl",
            "content": (
                "DEXTF holds under $5 M in TVL, significantly below competitors in the on-chain "
                "index category. Low liquidity raises concerns about slippage for larger positions."
            ),
        },
        {
            "url": "https://mock.tokenomics/dextf-unlocks",
            "content": (
                "Token unlock schedule shows 18 % of total DEXTF supply releasing over the next "
                "12 months. Team and advisor vesting cliff has passed, creating potential sell pressure."
            ),
        },
        {
            "url": "https://mock.founders/dextf-team",
            "content": (
                "DEXTF founding team carries strong TradFi backgrounds — prior roles at Goldman Sachs "
                "and Citadel. Institutional focus distinguishes them from retail-oriented DeFi protocols."
            ),
        },
    ],
    "solana": [
        {
            "url": "https://mock.solanabeach/uptime",
            "content": (
                "Solana network uptime improved to 99.9 % following QUIC and Gulf Stream upgrades. "
                "Previous outage history is no longer the primary concern for institutional adopters."
            ),
        },
        {
            "url": "https://mock.dextracker/solana-volume",
            "content": (
                "Meme-coin activity on Solana's DEX ecosystem drove a 300 % surge in daily trading "
                "volume. Pump.fun generates over 20,000 new token launches per day."
            ),
        },
        {
            "url": "https://mock.firedancer/client",
            "content": (
                "Firedancer, Jump Crypto's independent Solana validator client, nears mainnet launch. "
                "A second production client reduces systemic risk from software bugs significantly."
            ),
        },
        {
            "url": "https://mock.staking/sol-apy",
            "content": (
                "Solana staking yields stabilized at ~7.2 % APY after the inflation schedule "
                "adjustment. Validator count surpassed 2,000, improving decentralization metrics."
            ),
        },
        {
            "url": "https://mock.institutions/solana-adoption",
            "content": (
                "Franklin Templeton and VanEck launched Solana-based products. "
                "Visa's USDC settlement pilot on Solana processed over $1 B in transactions."
            ),
        },
    ],
}

# Fallback for unknown tokens
_GENERIC_RESULTS: list[dict] = [
    {
        "url": "https://mock.market/crypto-overview",
        "content": (
            "Crypto market shows mixed signals amid macro uncertainty. Bitcoin dominance holds at "
            "52 %, suggesting a broad altcoin season has not started. Total market cap ~$2.4 T."
        ),
    },
    {
        "url": "https://mock.onchain/accumulation",
        "content": (
            "On-chain metrics across major assets indicate an accumulation phase. Wallets holding "
            "1–10 tokens increased on several networks — historically a bullish signal."
        ),
    },
    {
        "url": "https://mock.trading/volume",
        "content": (
            "Spot trading volume across major CEXs is down 15 % from the monthly average. "
            "Reduced volume during consolidation is common before a directional move."
        ),
    },
    {
        "url": "https://mock.devactivity/quarterly",
        "content": (
            "Developer activity remains strong across the top-20 crypto projects by market cap. "
            "GitHub commits and new repository creation continue to grow year-over-year."
        ),
    },
    {
        "url": "https://mock.regulatory/clarity",
        "content": (
            "Regulatory clarity improving in the EU (MiCA), Hong Kong, and Singapore. "
            "The US remains the primary source of uncertainty for institutional crypto adoption."
        ),
    },
]

# ── Keyword → bucket mapping ──────────────────────────────────────────────────

_ALIASES: dict[str, str] = {
    "btc":      "bitcoin",
    "bitcoin":  "bitcoin",
    "eth":      "ethereum",
    "ether":    "ethereum",
    "ethereum": "ethereum",
    "dextf":    "dextf",
    "memento":  "dextf",
    "sol":      "solana",
    "solana":   "solana",
}


def _match_bucket(text: str) -> str | None:
    lowered = text.lower()
    for alias, bucket in _ALIASES.items():
        if alias in lowered:
            return bucket
    return None


# ── Public interface (same signature as the old Tavily wrapper) ───────────────

async def search_crypto(token_name: str, context: str = "") -> list[dict]:
    """Return mock search results for *token_name*.  No network I/O."""
    bucket  = _match_bucket(token_name) or _match_bucket(context)
    results = _RESULTS.get(bucket, _GENERIC_RESULTS) if bucket else _GENERIC_RESULTS

    logger.info(
        "mock_search",
        token=token_name,
        context=context or None,
        matched=bucket or "generic",
        n=len(results),
    )
    return results
