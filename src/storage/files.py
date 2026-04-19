from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class ReportFileManager:
    def __init__(self, output_dir: str = "data/reports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_markdown(self, content: str, label: str = "manual") -> Path:
        date_prefix = datetime.now().strftime("%Y%m%d%H%M")
        path = self.output_dir / f"{date_prefix}-{label}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def write_json(self, payload: dict, label: str = "manual") -> Path:
        date_prefix = datetime.now().strftime("%Y%m%d%H%M")
        path = self.output_dir / f"{date_prefix}-{label}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
