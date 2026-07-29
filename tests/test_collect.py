from pathlib import Path
import json

from candidatura_agent.collect import run_collection


def test_collection_reuses_pipeline_with_browser_disabled(tmp_path: Path):
    calls = []

    def pipeline(config, root):
        calls.append((config, root))
        return {"discovered": 2, "ingested": 2}

    config = {
        "source_json": "jobs.json",
        "browser_enabled": True,
        "linkedin": {"enabled": True},
    }

    result = run_collection(config, tmp_path, pipeline=pipeline)

    assert result == {"discovered": 2, "ingested": 2}
    assert calls == [({
        "source_json": "jobs.json",
        "browser_enabled": False,
        "linkedin": {"enabled": True},
    }, tmp_path)]
    assert config["browser_enabled"] is True


def test_collection_preserves_a_recent_nonempty_hourly_feed(tmp_path: Path):
    source = tmp_path / "jobs.json"
    source.write_text(json.dumps([{"id": "recent-1"}]))

    def must_not_run(config, root):
        raise AssertionError("a coleta recente seria apagada antes do relatório")

    result = run_collection(
        {"source_json": str(source), "browser_enabled": True},
        tmp_path,
        pipeline=must_not_run,
    )

    assert result == {"status": "reused", "discovered": 1, "ingested": None}
    assert json.loads(source.read_text()) == [{"id": "recent-1"}]
