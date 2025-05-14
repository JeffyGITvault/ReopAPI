import pytest
from app.api.agents.agent3_profile_people import profile_people

def test_profile_people_basic(monkeypatch):
    # Mock fetch_google_signals and enrich_with_public_signals to avoid real API calls
    monkeypatch.setattr("app.api.agents.agent3_profile_people.fetch_google_signals", lambda person, company: "Google result")
    monkeypatch.setattr("app.api.agents.agent3_profile_people.enrich_with_public_signals", lambda person, company: "Public profile")
    monkeypatch.setattr("app.api.agents.agent3_profile_people.infer_role_focus", lambda person, company, title=None: "Role focus")
    monkeypatch.setattr("app.api.agents.agent3_profile_people.check_filings_mention", lambda person, company: "Mentioned in filings")
    monkeypatch.setattr("app.api.agents.agent3_profile_people.infer_stack_from_job_posts", lambda company, business_unit_keywords=None: "Tech stack")
    people = ["Jane Doe"]
    company = "TestCo"
    titles = ["CFO"]
    result = profile_people(people, company, titles)
    assert isinstance(result, list)
    assert result[0]["name"] == "Jane Doe"
    assert result[0]["title"] == "CFO"
    assert "signals" in result[0] 