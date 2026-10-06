"""Optional semantic embeddings for clause retrieval.

Lexical retrieval needs a shared word to find a clause; embeddings let a paraphrase
with no shared word still match by meaning ("telefonni birovga o'tkazsam" ~ the
third-party registration clause). This module provides a small embedding callable
and the cosine helper; it is entirely optional - when no embedding provider is
configured the retriever stays purely lexical, so tests and offline runs are
unaffected and no network call is made.

Clause vectors are precomputed once (see scripts) and stored in a data file, so a
turn embeds only the short query. Vectors use text-embedding-3-small at 256
dimensions - enough to separate ~60 clauses, small enough to ship in the repo.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable

EmbedText = Callable[[str], Awaitable[list[float]]]

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIMENSIONS = 256


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors, 0.0 when either is degenerate."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def build_openai_embed(
    *,
    api_key: str,
    model: str = EMBED_MODEL,
    dimensions: int = EMBED_DIMENSIONS,
    timeout_seconds: float = 15.0,
) -> EmbedText:
    """Return an async callable that embeds one text via the OpenAI embeddings API."""
    import httpx

    async def embed(text: str) -> list[float]:
        payload = {"model": model, "input": text, "dimensions": dimensions}
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return [float(x) for x in data["data"][0]["embedding"]]

    return embed
