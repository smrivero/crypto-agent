from pathlib import Path

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load full .env into os.environ (pydantic alone only maps declared fields).
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    openai_api_key: str = "sk-placeholder"
    openai_base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-5.4-mini"

    # API server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False

    # Agent behaviour
    max_search_results: int = 5
    agent_timeout: int = 120

    # Tavily (web search — https://tavily.com). Empty → tools/web_search uses mock.
    tavily_api_key: str = ""

    # Blockchain RPC (optional — public fallback used if empty)
    ethereum_rpc_url: str = ""
    base_rpc_url: str = ""
    polygon_rpc_url: str = ""
    arbitrum_rpc_url: str = ""

    # Block explorer API keys (optional — enables holder count)
    etherscan_api_key: str = ""
    basescan_api_key: str = ""
    polygonscan_api_key: str = ""
    arbiscan_api_key: str = ""

    # x402 payment (Base Sepolia testnet)
    x402_network: str = "base-sepolia"
    x402_public_facilitator_url: str = Field(
        default="https://x402.org/facilitator",
        validation_alias=AliasChoices(
            "x402_public_facilitator_url",
            "x402_facilitator_url",
        ),
    )
    x402_receiving_wallet_address: str = ""
    x402_demo_price: str = "$0.01"

    # Coinbase CDP x402 facilitator (https://api.cdp.coinbase.com/platform/v2/x402)
    cdp_api_key_id: str = ""
    cdp_api_key_secret: str = ""
    cdp_project_id: str = ""

    # DEV ONLY — buyer wallet for x402 testnet (scripts + /x402/dev-sign). Never commit.
    evm_private_key: str = ""


settings = Settings()
