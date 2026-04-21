from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlparse


def normalize_title(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[#【】\[\]()（）:：!！?？|/\\\-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def format_markdown_link(url: str | None, text: str | None = None, *, max_length: int = 48) -> str:
    normalized_url = (url or "").strip()
    if not normalized_url:
        return "暂无"

    display_text = (text or "").strip()
    if not display_text:
        display_text = _shorten_url(normalized_url, max_length=max_length)

    return f"[{display_text}]({normalized_url})"


def _shorten_url(url: str, *, max_length: int) -> str:
    if len(url) <= max_length:
        return url

    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    path = parsed.path if parsed.netloc else ""
    compact_path = path.rstrip("/")
    last_segment = compact_path.rsplit("/", 1)[-1] if compact_path else ""

    if host and last_segment:
        candidate = f"{host}/.../{last_segment}"
        if len(candidate) <= max_length:
            return candidate

    if host and len(host) <= max_length:
        return f"{host}/..."

    if max_length <= 3:
        return url[:max_length]
    return f"{url[:max_length - 3]}..."
