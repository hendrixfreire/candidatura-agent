"""Coleta LinkedIn integrada, sem abrir navegador nem processar formulários."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from .hourly import run_pipeline


def run_collection(
    config: dict, root: Path, *, pipeline: Callable = run_pipeline,
) -> dict:
    source = Path(config["source_json"]).expanduser()
    if not source.is_absolute():
        source = root / source
    try:
        jobs = json.loads(source.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        jobs = []
    if jobs and time.time() - source.stat().st_mtime <= 45 * 60:
        return {"status": "reused", "discovered": len(jobs), "ingested": None}
    collection_config = dict(config)
    collection_config["browser_enabled"] = False
    return pipeline(collection_config, root)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / "config.json").read_text())
    result = run_collection(config, root)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
