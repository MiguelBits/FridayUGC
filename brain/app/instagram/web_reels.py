"""Reel discovery when mobile POST endpoints reject browser cookie sessions."""

from __future__ import annotations

import logging
import random
from typing import Any

logger = logging.getLogger(__name__)

_WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)


def _is_reel_media(media: Any) -> bool:
    product_type = getattr(media, "product_type", None)
    if product_type == "clips":
        return True
    media_type = getattr(media, "media_type", None)
    return media_type in (2, 8) or str(media_type) in ("2", "8")


def _filter_reels(medias: list[Any], amount: int) -> list[Any]:
    out: list[Any] = []
    for media in medias:
        if _is_reel_media(media):
            out.append(media)
        if len(out) >= amount:
            break
    return out


def _web_api_headers(cl: Any) -> dict[str, str]:
    csrf = ""
    token_fn = getattr(cl, "token", None)
    if callable(token_fn):
        csrf = str(token_fn() or "")
    if not csrf:
        csrf = str((cl.settings.get("cookies") or {}).get("csrftoken") or "")
    return {
        "User-Agent": _WEB_UA,
        "X-IG-App-ID": "936619743392459",
        "X-CSRFToken": csrf,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/reels/",
        "Origin": "https://www.instagram.com",
    }


def fetch_reels_web_discover(cl: Any, amount: int) -> list[Any]:
    """Try instagram.com web API for clips/discover (browser session)."""
    from instagrapi.extractors import extract_media_v1

    result = cl.private_request(
        "clips/discover/",
        data=" ",
        params={"max_id": ""},
        domain="www.instagram.com",
        with_signature=False,
        headers=_web_api_headers(cl),
    )
    medias: list[Any] = []
    for row in result.get("items") or []:
        if not isinstance(row, dict):
            continue
        media = row.get("media")
        if isinstance(media, dict):
            medias.append(extract_media_v1(media))
        if len(medias) >= amount:
            break
    return medias[:amount]


def fetch_reels_hashtag_gql(cl: Any, tag: str, amount: int) -> list[Any]:
    """Public/web GraphQL hashtag feed — works with injected browser sessionid."""
    cl.inject_sessionid_to_public()
    medias, _ = cl.hashtag_medias_paginated_gql(tag, amount=max(amount * 4, 12))
    return _filter_reels(medias, amount)


def fetch_reels_search(cl: Any, query: str, amount: int) -> list[Any]:
    """Reels SERP (GET) — sometimes allowed when POST clips/* is blocked."""
    from instagrapi.extractors import extract_media_v1

    result = cl.fbsearch_reels_serp(query)
    grid = result.get("media_grid") if isinstance(result, dict) else None
    if not isinstance(grid, dict):
        return []
    medias: list[Any] = []
    for media in cl._fbsearch_media_grid_nodes(grid):
        medias.append(extract_media_v1(media))
        if len(medias) >= amount:
            break
    return medias[:amount]


def fetch_reels_web_fallbacks(cl: Any, amount: int, tags: list[str]) -> tuple[list[Any], str]:
    """Ordered web-friendly sources for cookie-only sessions."""
    errors: list[str] = []

    for query in ("reels", "fitness reels", "gym reels"):
        try:
            items = fetch_reels_search(cl, query, amount)
            if items:
                return items, f"fbsearch_reels_serp({query!r})"
        except Exception as exc:
            errors.append(f"search {query!r}: {exc}")

    shuffled = list(tags)
    random.shuffle(shuffled)
    for tag in shuffled:
        try:
            items = fetch_reels_hashtag_gql(cl, tag, amount)
            if items:
                return items, f"hashtag_gql(#{tag})"
        except Exception as exc:
            errors.append(f"hashtag_gql #{tag}: {exc}")

    try:
        items = fetch_reels_web_discover(cl, amount)
        if items:
            return items, "www.clips/discover"
    except Exception as exc:
        errors.append(f"www.clips/discover: {exc}")

    detail = "; ".join(errors) if errors else "no web reel sources returned media"
    raise RuntimeError(detail)
