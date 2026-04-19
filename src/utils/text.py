from __future__ import annotations

import re
from collections.abc import Iterable


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
