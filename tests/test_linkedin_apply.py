from candidatura_agent.linkedin_apply import select_offsite_apply_url


def test_select_offsite_apply_url_ignores_linkedin_and_uses_apply_link():
    anchors = [
        {"href": "https://www.linkedin.com/company/acme", "text": "Acme"},
        {"href": "https://example.com/privacy", "text": "Privacy"},
        {"href": "https://jobs.lever.co/acme/abc", "text": "Apply"},
    ]

    assert select_offsite_apply_url(anchors) == "https://jobs.lever.co/acme/abc"


def test_select_offsite_apply_url_reads_data_url_from_apply_button():
    anchors = [
        {"href": "", "url": "https://jobs.example.com/role/1", "text": "Aplicar agora"},
    ]

    assert select_offsite_apply_url(anchors) == "https://jobs.example.com/role/1"


def test_select_offsite_apply_url_returns_none_without_external_apply_action():
    anchors = [
        {"href": "https://www.linkedin.com/jobs/view/1", "text": "Apply"},
        {"href": "https://example.com/privacy", "text": "Privacy"},
    ]

    assert select_offsite_apply_url(anchors) is None
