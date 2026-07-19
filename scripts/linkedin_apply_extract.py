#!/usr/bin/env python3
"""Extrai destinos Apply externos de vagas LinkedIn em uma sessão autenticada.

Conecta apenas ao contexto dedicado em localhost:9226. Quando não há sessão
válida, encerra silenciosamente e não altera o banco.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import TimeoutError, sync_playwright

from candidatura_agent.assets import record_job_resolution
from candidatura_agent.db import Database
from candidatura_agent.linkedin_apply import select_offsite_apply_url

ROOT = Path(__file__).resolve().parents[1]


def _is_external_https(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and bool(host) and host != "linkedin.com" and not host.endswith(".linkedin.com")


def _click_apply_and_capture_external_url(page, context) -> str | None:
    """Clica somente no botão externo do LinkedIn; nunca interage com o formulário."""
    button = page.get_by_text("Candidatar-se", exact=True)
    if button.count() != 1:
        return None
    existing = {item.url for item in context.pages}
    target = page
    try:
        with context.expect_page(timeout=8_000) as opened:
            button.click()
        target = opened.value
        target.wait_for_load_state("domcontentloaded", timeout=45_000)
    except TimeoutError:
        page.wait_for_timeout(2_500)
        opened_pages = [item for item in context.pages if item.url not in existing]
        if opened_pages:
            target = opened_pages[-1]
    try:
        return target.url if _is_external_https(target.url) else None
    finally:
        if target is not page and not target.is_closed():
            target.close()


def main() -> int:
    config = json.loads((ROOT / "config.json").read_text())
    db_path = Path(config["database"])
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    db = Database(db_path)
    db.initialize()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp("http://127.0.0.1:9226")
            context = browser.contexts[0]
            has_session = any(cookie.get("name") == "li_at" for cookie in context.cookies("https://www.linkedin.com"))
            if not has_session:
                print(json.dumps({"status": "login_required"}))
                return 0
            page = context.new_page()
            outcomes = []
            for job in db.asset_queue(limit=10, stage="resolve"):
                page.goto(job["source_url"], wait_until="domcontentloaded", timeout=90_000)
                anchors = page.locator("a[href], [data-url], [data-apply-url]").evaluate_all(
                    """els => els.map(el => ({
                        href: el.href || '',
                        url: el.dataset.applyUrl || el.dataset.url || '',
                        text: el.innerText || el.getAttribute('aria-label') || ''
                    }))"""
                )
                url = select_offsite_apply_url(anchors)
                if url is None:
                    url = _click_apply_and_capture_external_url(page, context)
                if url is None:
                    outcomes.append({"job_id": job["id"], "status": "no_offsite_apply_url"})
                    continue
                try:
                    ats = record_job_resolution(
                        db, int(job["id"]), url, company=job["company"],
                        resolution_source="authenticated_linkedin_apply_link",
                    )
                except ValueError:
                    outcomes.append({"job_id": job["id"], "status": "unsupported_ats"})
                    continue
                outcomes.append({"job_id": job["id"], "status": "resolved", "ats": ats})
            if outcomes:
                print(json.dumps(outcomes, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"status": "extractor_failed", "error": type(exc).__name__}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
