"""Descoberta de vagas pelo endpoint público Guest Jobs do LinkedIn."""

from __future__ import annotations

import re
from collections.abc import Callable
from html import unescape
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .assets import extract_linkedin_description

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.5",
}


def _fetch_url(url: str) -> str:
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=12) as response:
        return response.read().decode("utf-8", "replace")


def _clean_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).strip()


def _extract(pattern: str, value: str) -> str:
    match = re.search(pattern, value, re.DOTALL | re.IGNORECASE)
    return _clean_html(match.group(1)) if match else ""


def _parse_search_results(html: str) -> list[dict]:
    jobs = []
    for match in re.finditer(
        r'data-entity-urn="urn:li:jobPosting:(\d+)"(.*?)</li>', html, re.DOTALL,
    ):
        job_id, card = match.groups()
        date_match = re.search(
            r'<time[^>]*datetime="([^"]*)"[^>]*>(.*?)</time>', card,
            re.DOTALL | re.IGNORECASE,
        )
        jobs.append({
            "id": job_id,
            "title": _extract(r"base-search-card__title[^>]*>(.*?)</h3>", card),
            "company": _extract(
                r"(?:hidden-nested-link[^>]*>|base-search-card__subtitle[^>]*>)(.*?)</(?:a|h4)>",
                card,
            ),
            "location": _extract(r"job-search-card__location[^>]*>(.*?)</span>", card),
            "date": date_match.group(1).strip() if date_match else "",
            "date_label": _clean_html(date_match.group(2)) if date_match else "",
            "url": f"https://www.linkedin.com/jobs/view/{job_id}",
        })
    return jobs


def _build_searches(keywords: list[str]) -> list[dict[str, str]]:
    searches = []
    for location, work_type in (("Brazil", "2"), ("São Paulo, Brazil", "3")):
        for keyword in keywords:
            search = {
                "keywords": keyword,
                "location": location,
                "f_WT": work_type,
                "f_TPR": "r2592000",
                "sortBy": "DD",
            }
            if not any(level in keyword.lower() for level in ("manager", "head", "director")):
                search["f_E"] = "4"
            searches.append(search)
    return searches


def _heuristic_score(job: dict) -> tuple[int, str]:
    title = str(job.get("title") or "").lower()
    location = str(job.get("location") or "").lower()
    high = (
        "data engineer", "analytics engineer", "bi manager", "data analytics",
        "ai engineer", "machine learning", "head de dados", "gerente de dados",
        "data tech lead", "chapter lead", "coordenador", "coordenadora",
    )
    medium = (
        "data analyst", "data scientist", "business intelligence", "bi ", "etl",
        "bigquery", "airflow", "spark", "dbt", "python", "sql",
    )
    senior = (
        "senior", "sênior", "lead", "manager", "head", "director", "coordenador",
        "coordenadora", "gerente", "principal", "staff",
    )
    junior = ("junior", "júnior", "jr", "intern", "estagiário", "trainee", "pleno")
    if any(term in title for term in junior):
        return 1, "junior/mid level"

    points = 0
    reasons = []
    if any(term in title for term in high):
        points += 2
        reasons.append("high stack")
    elif any(term in title for term in medium):
        points += 1
        reasons.append("mid stack")
    points += 2
    reasons.append("senior+" if any(term in title for term in senior) else "mid/senior (assumed)")
    if any(term in location for term in ("brazil", "brasil", "são paulo", "sao paulo")):
        points += 1
        reasons.append("remote/BR" if "paulo" not in location else "SP")
    stars = 5 if points >= 4 else max(1, points + 1)
    return stars, ", ".join(reasons)


def job_key(title: str, company: str) -> str:
    """Normaliza título e empresa para reconhecer repostagens com outro ID."""
    values = []
    for value in (title, company):
        normalized = unescape(_clean_html(value)).strip().lower()
        for pattern in (r"\s*[-–—]\s*.*$", r"\s*\(.*?\)\s*$", r"\s*\|.*$"):
            normalized = re.sub(pattern, "", normalized).strip()
        values.append(normalized)
    return "||".join(values)


def _detail(html: str) -> dict[str, str | bool]:
    text = " ".join(_clean_html(html).split())
    mode_match = re.search(r"\b(Remote|Remoto|Hybrid|Híbrido|On-site|Presencial)\b", text, re.I)
    description = extract_linkedin_description(html)
    return {
        "work_mode": mode_match.group(1) if mode_match else "",
        "description": description,
        "closed": (
            "no longer accepting applications" in text.lower()
            or "não aceita mais" in text.lower()
        ),
    }


def discover_linkedin_jobs(
    config: dict, *, known_external_ids: set[str] | None = None,
    known_job_keys: set[str] | None = None,
    fetch_url: Callable[[str], str] = _fetch_url,
) -> list[dict]:
    """Busca, deduplica, filtra e enriquece vagas elegíveis do LinkedIn."""
    keywords = list(config.get("keywords") or [])
    blocklist = [str(item).lower() for item in config.get("company_blocklist", [])]
    max_pages = int(config.get("max_pages", 2))
    max_jobs = int(config.get("max_jobs", 8))
    known_external_ids = known_external_ids or set()
    known_job_keys = known_job_keys or set()
    found: dict[str, dict] = {}

    for search in _build_searches(keywords):
        for page in range(max_pages):
            url = f"{SEARCH_URL}?{urlencode({**search, 'start': page * 25})}"
            try:
                html = fetch_url(url)
            except Exception:
                continue
            for job in _parse_search_results(html):
                found.setdefault(job["id"], job)

    eligible = []
    batch_keys = set()
    for job in found.values():
        if job["id"] in known_external_ids:
            continue
        key = job_key(job["title"], job["company"])
        if key in known_job_keys or key in batch_keys:
            continue
        batch_keys.add(key)
        title = job["title"].lower()
        location = job["location"].lower()
        company = job["company"].lower()
        if any(term in title for term in ("junior", "júnior", "jr", "intern", "estagiário", "trainee")):
            continue
        if not any(term in location for term in ("brazil", "brasil", "são paulo", "sao paulo")):
            continue
        if any(term in company for term in blocklist):
            continue
        eligible.append(job)

    jobs = []
    for job in eligible[:max_jobs]:
        try:
            html = fetch_url(DETAIL_URL.format(job_id=job["id"]))
        except Exception:
            continue
        details = _detail(html)
        if details["closed"] or str(details["work_mode"]).lower() not in {
            "remote", "remoto", "hybrid", "híbrido",
        }:
            continue
        score, reason = _heuristic_score(job)
        jobs.append({
            **job,
            "work_mode": details["work_mode"],
            "description": details["description"],
            "heuristic_score": score,
            "heuristic_reason": reason,
        })
    return jobs
