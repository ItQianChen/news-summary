from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

from src.utils import get_logger


class AIClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        self.model_name = os.getenv("MODEL_NAME", "gpt-4o-mini").strip()
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "").strip()
        self.timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
        self.max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
        self.logger = get_logger(__name__)
        self._client: OpenAI | None = None

        if self.is_configured():
            client_kwargs: dict[str, Any] = {
                "api_key": self.api_key,
                "timeout": self.timeout_seconds,
                "max_retries": self.max_retries,
            }
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            self._client = OpenAI(**client_kwargs)

    def is_configured(self) -> bool:
        return bool(self.api_key and self.model_name)

    def complete(self, system_prompt: str, user_prompt: str, *, temperature: float | None = None) -> str:
        if not self._client:
            return ""
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature if temperature is None else temperature,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            self.logger.warning("AI completion failed: %s", exc)
            return ""

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        text = self.complete(system_prompt, user_prompt)
        return self.extract_json(text)

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self._client or not self.embedding_model or not texts:
            return None
        try:
            response = self._client.embeddings.create(model=self.embedding_model, input=texts)
            return [item.embedding for item in response.data]
        except Exception as exc:
            self.logger.warning("embedding request failed: %s", exc)
            return None

    @staticmethod
    def extract_json(text: str) -> dict[str, Any] | None:
        if not text:
            return None
        text = text.strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
