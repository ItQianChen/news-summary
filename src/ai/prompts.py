from __future__ import annotations

from pathlib import Path


class PromptRepository:
    def __init__(self, prompt_dir: str = "config/prompts") -> None:
        self.prompt_dir = Path(prompt_dir)

    def load(self, name: str) -> str:
        path = self.prompt_dir / name
        return path.read_text(encoding="utf-8")
