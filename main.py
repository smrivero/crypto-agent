"""
Entry point — two modes:

  python main.py                       → start FastAPI server
  python main.py "Analyze DEXTF token" → run a single query in the terminal
"""

import asyncio
import sys

import uvicorn

from config.logging import configure_logging
from config.settings import settings


def serve() -> None:
    configure_logging(debug=settings.debug)
    uvicorn.run(
        "api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )


async def _run_query(query: str) -> None:
    configure_logging(debug=True)
    from agents.research_agent import CryptoResearchAgent

    agent = CryptoResearchAgent()
    response = await agent.research(query)

    if response.success and response.report:
        r = response.report
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"  TOKEN      : {r.token}")
        print(f"  CONFIDENCE : {r.confidence_score:.0%}")
        print(f"{sep}")
        print(f"\nSUMMARY\n{r.summary}")
        print("\nBULLISH")
        for p in r.bullish_points:
            print(f"  + {p}")
        print("\nBEARISH")
        for p in r.bearish_points:
            print(f"  - {p}")
        print("\nRISKS")
        for p in r.risks:
            print(f"  ! {p}")
        print(f"\nSOURCES  : {len(r.sources)} URLs")
        print(f"TIME     : {response.processing_time_ms} ms\n")
    else:
        print(f"\nError: {response.error}\n", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] != "serve":
        asyncio.run(_run_query(" ".join(args)))
    else:
        serve()


if __name__ == "__main__":
    main()
