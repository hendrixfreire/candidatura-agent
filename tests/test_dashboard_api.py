"""Testes da fatia vertical da GUI local: API e UI somente leitura.

Cobre filtros, detalhe, eventos (auditoria) e preservação dos endpoints
originais /api/snapshot e /api/feedback. Nenhum endpoint de envio.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

from candidatura_agent.dashboard import make_handler
from candidatura_agent.db import Database


def _start_server(db: Database) -> tuple[ThreadingHTTPServer, int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(db, 10))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def _stop(server: ThreadingHTTPServer) -> None:
    server.shutdown()
    server.server_close()


def _get(port: int, path: str) -> tuple[int, object]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as resp:
        body = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        if "json" in ctype:
            return resp.status, json.loads(body)
        return resp.status, body.decode("utf-8")


def _post(port: int, path: str, payload: dict) -> tuple[int, object]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data, headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        body = resp.read()
        return resp.status, json.loads(body) if body else None


def _seed(db: Database) -> dict[str, int]:
    a = db.upsert_job({
        "external_id": "1", "title": "Data Engineer", "company": "Acme",
        "location": "São Paulo, BR", "source_url": "https://x/1",
        "ats": "greenhouse", "fit_score": 85, "status": "qualified",
        "fit_reasons": ["python", "sql"], "blockers": [],
        "description": "Vaga de dados com Python e SQL.",
    })
    b = db.upsert_job({
        "external_id": "2", "title": "BI Manager", "company": "Beta",
        "location": "Remote, US", "source_url": "https://x/2",
        "ats": "ashby", "fit_score": 40, "status": "blocked",
        "fit_reasons": [], "blockers": ["salário não informado"],
    })
    db.update_assessment(b, 40, [], ["salário não informado"], "blocked")
    return {"a": a, "b": b}


def test_jobs_list_returns_all_by_default(tmp_path: Path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    _seed(db)
    server, port = _start_server(db)
    try:
        status, payload = _get(port, "/api/jobs")
        assert status == 200
        assert len(payload["jobs"]) == 2
        assert {j["title"] for j in payload["jobs"]} == {"Data Engineer", "BI Manager"}
    finally:
        _stop(server)


def test_jobs_list_filters_by_status(tmp_path: Path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    _seed(db)
    server, port = _start_server(db)
    try:
        status, payload = _get(port, "/api/jobs?" + urlencode({"status": "blocked"}))
        assert status == 200
        assert len(payload["jobs"]) == 1
        assert payload["jobs"][0]["status"] == "blocked"
    finally:
        _stop(server)


def test_jobs_list_supports_pagination(tmp_path: Path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    _seed(db)
    server, port = _start_server(db)
    try:
        _, first = _get(port, "/api/jobs?limit=1&offset=0")
        _, second = _get(port, "/api/jobs?limit=1&offset=1")
        assert isinstance(first, dict)
        assert isinstance(second, dict)
        assert first["count"] == 2
        assert first["limit"] == 1
        assert first["jobs"][0]["id"] != second["jobs"][0]["id"]
    finally:
        _stop(server)


def test_jobs_list_filters_by_ats(tmp_path: Path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    _seed(db)
    server, port = _start_server(db)
    try:
        _, payload = _get(port, "/api/jobs?" + urlencode({"ats": "greenhouse"}))
        assert len(payload["jobs"]) == 1
        assert payload["jobs"][0]["ats"] == "greenhouse"
    finally:
        _stop(server)


def test_jobs_list_search_by_title(tmp_path: Path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    _seed(db)
    server, port = _start_server(db)
    try:
        _, payload = _get(port, "/api/jobs?" + urlencode({"q": "data engineer"}))
        assert len(payload["jobs"]) == 1
        assert payload["jobs"][0]["title"] == "Data Engineer"
    finally:
        _stop(server)


def test_job_detail_returns_full_record_and_blockers_parsed(tmp_path: Path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    ids = _seed(db)
    server, port = _start_server(db)
    try:
        status, payload = _get(port, f"/api/jobs/{ids['b']}")
        assert status == 200
        assert payload["job"]["id"] == ids["b"]
        assert payload["job"]["blockers"] == ["salário não informado"]
        assert payload["job"]["fit_reasons"] == []
    finally:
        _stop(server)


def test_job_detail_404_for_missing(tmp_path: Path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    server, port = _start_server(db)
    try:
        try:
            _get(port, "/api/jobs/9999")
            assert False, "esperado 404"
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
    finally:
        _stop(server)


def test_job_events_returns_audit_trail(tmp_path: Path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    ids = _seed(db)
    server, port = _start_server(db)
    try:
        status, payload = _get(port, f"/api/jobs/{ids['b']}/events")
        assert status == 200
        kinds = [e["kind"] for e in payload["events"]]
        assert "assessed" in kinds
        assert len(payload["events"]) >= 1
    finally:
        _stop(server)


def test_snapshot_endpoint_preserved(tmp_path: Path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    _seed(db)
    server, port = _start_server(db)
    try:
        status, payload = _get(port, "/api/snapshot")
        assert status == 200
        assert "stats" in payload
        assert "daily_target" in payload
        assert "jobs" in payload
    finally:
        _stop(server)


def test_feedback_endpoint_preserved(tmp_path: Path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    ids = _seed(db)
    server, port = _start_server(db)
    try:
        status, _ = _post(port, "/api/feedback", {
            "job_id": ids["a"], "rating": "good", "reason": "ok",
        })
        assert status == 200
        feedback = db.list_feedback()
        assert feedback[0]["rating"] == "good"
    finally:
        _stop(server)


def test_home_serves_html_without_submit_button(tmp_path: Path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    server, port = _start_server(db)
    try:
        status, body = _get(port, "/")
        assert status == 200
        assert isinstance(body, str)
        assert "<!doctype html>" in body.lower()
        # nenhum botão de envio nesta fase
        assert "enviar candidatura" not in body.lower()
        assert "/api/jobs/" in body  # a UI conhece o endpoint de detalhe
        assert "Array.isArray(k)" in body  # aceita listas já parseadas pela API
        assert "['http:','https:'].includes(u.protocol)" in body
        assert "family=Doto" in body
        assert "Space+Grotesk" in body
        assert "Space+Mono" in body
        assert "Meta mínima de hoje" in body
        assert "localStorage.getItem('ca-theme')" in body
    finally:
        _stop(server)


def test_no_submit_endpoint_exists(tmp_path: Path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    _seed(db)
    server, port = _start_server(db)
    try:
        for path in ("/api/jobs/1/submit", "/api/submit", "/api/jobs/1/apply"):
            try:
                _get(port, path)
                assert False, f"{path} não deveria existir"
            except urllib.error.HTTPError as exc:
                assert exc.code == 404
    finally:
        _stop(server)
