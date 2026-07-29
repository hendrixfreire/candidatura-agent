"""Dashboard local com fila, auditoria, filtros e feedback.

Fase 1 da GUI local (fatia vertical):
- Home operacional (somente leitura).
- Lista de vagas com filtros por status, ATS e busca textual.
- Detalhe da vaga com bloqueios e motivos de aderência.
- Trilha de auditoria (eventos) por vaga.
- Endpoints originais /api/snapshot e /api/feedback preservados.
- Nenhum endpoint de envio nesta fase.
"""

from __future__ import annotations

import json
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .db import Database
from .dashboard_page import HTML as PAGE_HTML



def _parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def dashboard_snapshot(db: Database, daily_target_min: int = 10) -> dict[str, Any]:
    jobs = db.list_jobs()
    stats = Counter(job["status"] for job in jobs)
    submitted = db.submitted_today()
    for job in jobs:
        for key in ("fit_reasons", "blockers"):
            job[key] = _parse_json_list(job.get(key))
    return {
        "stats": dict(stats),
        "daily_target": {
            "minimum": daily_target_min,
            "submitted": submitted,
            "gap": max(0, daily_target_min - submitted),
            "met": submitted >= daily_target_min,
            "unlimited": True,
        },
        "jobs": jobs,
        "feedback": db.list_feedback()[:100],
    }


def jobs_payload(db: Database, filters: dict[str, str]) -> dict[str, Any]:
    """Lista filtrada de vagas (somente leitura), com blockers/fit_reasons parseados."""
    kwargs: dict[str, Any] = {}
    if filters.get("status"):
        kwargs["status"] = filters["status"]
    if filters.get("ats"):
        kwargs["ats"] = filters["ats"]
    if filters.get("q"):
        kwargs["query_text"] = filters["q"]
    if filters.get("min_score"):
        try:
            kwargs["min_score"] = int(filters["min_score"])
        except ValueError:
            pass
    jobs = db.list_jobs(**kwargs)
    for job in jobs:
        for key in ("fit_reasons", "blockers"):
            job[key] = _parse_json_list(job.get(key))
    try:
        limit = min(200, max(1, int(filters.get("limit", "50"))))
        offset = max(0, int(filters.get("offset", "0")))
    except ValueError:
        limit, offset = 50, 0
    return {"jobs": jobs[offset : offset + limit], "count": len(jobs), "limit": limit, "offset": offset}


def job_detail_payload(db: Database, job_id: int) -> dict[str, Any] | None:
    job = db.get_job(job_id)
    if not job:
        return None
    for key in ("fit_reasons", "blockers"):
        job[key] = _parse_json_list(job.get(key))
    return {"job": job}


def job_events_payload(db: Database, job_id: int) -> dict[str, Any]:
    return {"events": db.list_events(job_id)}


def _job_id_from_path(path: str) -> int | None:
    parts = [p for p in path.split("/") if p]
    if len(parts) == 3 and parts[0] == "api" and parts[1] == "jobs":
        try:
            return int(parts[2])
        except ValueError:
            return None
    return None


def _is_job_events_path(path: str) -> int | None:
    parts = [p for p in path.split("/") if p]
    if len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "events":
        try:
            return int(parts[2])
        except ValueError:
            return None
    return None


def make_handler(db: Database, daily_target_min: int = 10):
    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.request.settimeout(30)

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: Any) -> None:
            self._send(
                status,
                json.dumps(payload, ensure_ascii=False).encode(),
                "application/json; charset=utf-8",
            )

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path in ("/", "/index.html"):
                self._send(200, PAGE_HTML.encode(), "text/html; charset=utf-8")
                return
            if path == "/api/snapshot":
                self._send_json(200, dashboard_snapshot(db, daily_target_min))
                return
            if path == "/api/health":
                self._send_json(200, {"ok": True})
                return
            if path == "/api/jobs":
                filters = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                self._send_json(200, jobs_payload(db, filters))
                return
            events_id = _is_job_events_path(path)
            if events_id is not None:
                if db.get_job(events_id) is None:
                    self._send_json(404, {"error": "job not found"})
                    return
                self._send_json(200, job_events_payload(db, events_id))
                return
            detail_id = _job_id_from_path(path)
            if detail_id is not None:
                payload = job_detail_payload(db, detail_id)
                if payload is None:
                    self._send_json(404, {"error": "job not found"})
                    return
                self._send_json(200, payload)
                return
            self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/api/feedback":
                self._send_json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                rating = payload.get("rating")
                if rating not in ("good", "bad", "irrelevant"):
                    raise ValueError("rating inválido")
                db.add_feedback(int(payload["job_id"]), rating, str(payload.get("reason") or "")[:500])
                self._send_json(200, {"ok": True})
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                self._send_json(400, {"error": str(exc)})

        def log_message(self, format: str, *args: Any) -> None:
            pass

    return Handler


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / "config.json").read_text())
    db_path = Path(config["database"])
    if not db_path.is_absolute():
        db_path = root / db_path
    db = Database(db_path)
    db.initialize()
    port = int(config.get("dashboard_port", 8765))
    server = ThreadingHTTPServer(
        ("127.0.0.1", port),
        make_handler(db, int(config.get("daily_target_min", 10))),
    )
    print(f"Dashboard: http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
