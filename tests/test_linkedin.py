from candidatura_agent.linkedin import discover_linkedin_jobs


SEARCH_HTML = """
<li data-entity-urn="urn:li:jobPosting:123">
  <h3 class="base-search-card__title">Senior Data Engineer</h3>
  <h4 class="base-search-card__subtitle"><a class="hidden-nested-link">Acme</a></h4>
  <span class="job-search-card__location">Brazil</span>
  <time datetime="2026-07-27">1 hour ago</time>
</li>
"""

DETAIL_HTML = """
<section><span>Remote</span><div class="show-more-less-html__markup">
Build reliable data pipelines with Python and SQL.
</div></section>
"""


def test_discovery_returns_normalized_remote_job_once_across_searches():
    requested = []

    def fetch(url: str) -> str:
        requested.append(url)
        return DETAIL_HTML if "jobPosting/123" in url else SEARCH_HTML

    jobs = discover_linkedin_jobs(
        {
            "keywords": ["data engineer"],
            "company_blocklist": [],
            "max_pages": 1,
            "max_jobs": 8,
        },
        fetch_url=fetch,
    )

    assert jobs == [{
        "id": "123",
        "title": "Senior Data Engineer",
        "company": "Acme",
        "location": "Brazil",
        "work_mode": "Remote",
        "date": "2026-07-27",
        "date_label": "1 hour ago",
        "url": "https://www.linkedin.com/jobs/view/123",
        "description": "Build reliable data pipelines with Python and SQL.",
        "heuristic_score": 5,
        "heuristic_reason": "high stack, senior+, remote/BR",
    }]
    assert sum("jobPosting/123" in url for url in requested) == 1


def test_discovery_skips_known_jobs_before_fetching_details():
    requested = []

    def fetch(url: str) -> str:
        requested.append(url)
        return SEARCH_HTML

    jobs = discover_linkedin_jobs(
        {"keywords": ["data engineer"], "max_pages": 1},
        known_external_ids={"123"},
        fetch_url=fetch,
    )

    assert jobs == []
    assert not any("jobPosting/123" in url for url in requested)


def test_discovery_continues_when_one_search_request_fails():
    searches = 0

    def fetch(url: str) -> str:
        nonlocal searches
        if "jobPosting/123" in url:
            return DETAIL_HTML
        searches += 1
        if searches == 1:
            raise TimeoutError("LinkedIn timeout")
        return SEARCH_HTML

    jobs = discover_linkedin_jobs(
        {"keywords": ["data engineer"], "max_pages": 1},
        fetch_url=fetch,
    )

    assert [job["id"] for job in jobs] == ["123"]


def test_discovery_skips_reposted_title_and_company_before_fetching_details():
    requested = []

    def fetch(url: str) -> str:
        requested.append(url)
        return SEARCH_HTML.replace("123", "456")

    jobs = discover_linkedin_jobs(
        {"keywords": ["data engineer"], "max_pages": 1},
        known_job_keys={"senior data engineer||acme"},
        fetch_url=fetch,
    )

    assert jobs == []
    assert not any("jobPosting/456" in url for url in requested)
