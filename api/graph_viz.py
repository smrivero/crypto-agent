"""Mermaid diagram generation from the compiled LangGraph."""

import pathlib
from functools import lru_cache

_DOCS = pathlib.Path("docs")

# LangGraph hardcodes light-lavender classDef colours that look broken on a
# dark background even when Mermaid's dark theme is active (classDef overrides
# theme variables at render time).  Replace them with our UI palette.
_COLOR_MAP = {
    "fill:#f2f0ff": "fill:#1a2332",   # default node  → dark-surface
    "fill:#bfb6fc": "fill:#1e3a5f",   # __end__ node  → deep-blue
}


def _apply_dark_colors(mmd: str) -> str:
    for src, dst in _COLOR_MAP.items():
        mmd = mmd.replace(src, dst)
    return mmd


@lru_cache(maxsize=1)
def get_mermaid() -> str:
    from graphs.research_graph import build_research_graph

    graph = build_research_graph()
    return _apply_dark_colors(graph.get_graph().draw_mermaid())


def save_to_docs() -> None:
    """Write the diagram to docs/research_graph.mmd (idempotent)."""
    _DOCS.mkdir(exist_ok=True)
    (_DOCS / "research_graph.mmd").write_text(get_mermaid(), encoding="utf-8")
