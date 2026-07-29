import json
from pathlib import Path

from candidatura_agent.hourly import (
    _allowed_ats_for_run, _browser_candidates, _profile_for_job, run_pipeline,
)


def test_browser_candidates_prioritize_brave_then_chrome_then_bundled():
    assert _browser_candidates({}) == [
        ("brave", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
        ("chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ("chromium", None),
    ]


def test_dry_run_can_probe_more_ats_without_expanding_submit_allowlist():
    config = {
        "allowed_ats": ["greenhouse"],
        "dry_run_allowed_ats": ["greenhouse", "factorial", "gupy", "peopleforce"],
    }
    assert _allowed_ats_for_run(config, auto_submit=False) == {
        "greenhouse", "factorial", "gupy", "peopleforce",
    }
    assert _allowed_ats_for_run(config, auto_submit=True) == {"greenhouse"}


def test_profile_for_job_uses_tailored_resume_when_required():
    profile = {"resume": "/tmp/generic.pdf", "resume_strategy": "tailor_per_job"}
    assert _profile_for_job(profile, {"resume_path": None}) is None
    tailored = _profile_for_job(profile, {"resume_path": "/tmp/company.pdf"})
    assert tailored["resume"] == "/tmp/company.pdf"


def test_hourly_pipeline_ingests_scores_and_writes_control(tmp_path: Path):
    source = tmp_path / "jobs.json"
    source.write_text(json.dumps([{
        "id": "1", "title": "Senior Analytics Engineer", "company": "Acme",
        "location": "Brazil", "url": "https://boards.greenhouse.io/acme/jobs/1",
        "description": "Python SQL BigQuery GCP lakehouse", "heuristic_score": 5,
    }]))
    profile = {
        "full_name": "Test", "target_titles": ["analytics engineer"],
        "preferred_skills": ["python", "sql", "bigquery", "gcp", "lakehouse"],
        "blocked_title_terms": ["junior"], "allowed_locations": ["brazil"],
        "min_fit_score": 70, "daily_target_min": 10,
    }
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile))
    config = {
        "source_json": str(source), "database": str(tmp_path / "state.db"),
        "profile": str(profile_path), "run_control": str(tmp_path / "control.json"),
        "browser_enabled": False, "auto_submit": False, "allowed_ats": ["greenhouse"],
        "min_fit_score": 70, "daily_target_min": 10,
    }

    result = run_pipeline(config, tmp_path)

    assert result["ingested"] == 1
    assert result["qualified"] == 1
    assert result["daily_target_min"] == 10
    assert result["target_gap"] == 10
    assert result["target_met"] is False
    assert "daily_limit" not in result
    assert json.loads((tmp_path / "control.json").read_text())["status"] == "ok"


def test_hourly_pipeline_discovers_jobs_before_ingesting_them(tmp_path: Path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({
        "target_titles": ["data engineer"],
        "preferred_skills": ["python", "sql"],
        "blocked_title_terms": ["junior"],
        "allowed_locations": ["brazil"],
        "min_fit_score": 70,
    }))
    source = tmp_path / "jobs.json"
    config = {
        "source_json": str(source),
        "database": str(tmp_path / "state.db"),
        "profile": str(profile_path),
        "run_control": str(tmp_path / "control.json"),
        "browser_enabled": False,
        "linkedin": {"enabled": True, "keywords": ["data engineer"]},
    }
    calls = []

    def discover(discovery_config, *, known_external_ids, known_job_keys):
        calls.append((discovery_config, known_external_ids, known_job_keys))
        return [{
            "id": "new-1", "title": "Senior Data Engineer", "company": "Acme",
            "location": "Brazil", "url": "https://www.linkedin.com/jobs/view/new-1",
            "description": "Python SQL", "heuristic_score": 5,
        }]

    result = run_pipeline(config, tmp_path, discover_jobs=discover)

    assert result["discovered"] == 1
    assert result["ingested"] == 1
    assert calls == [({"enabled": True, "keywords": ["data engineer"]}, set(), set())]
    assert json.loads(source.read_text())[0]["id"] == "new-1"
