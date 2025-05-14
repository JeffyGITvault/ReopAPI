import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from app.api.agents.agent1_fetch_sec import extract_10q_sections, fetch_10q

# Unit test for extract_10q_sections
def test_extract_10q_sections_basic():
    html = """
    <html><body>
    <b>Item 1. Financial Statements</b>
    <table><tr><td>Revenue</td><td>100</td></tr></table>
    <b>Item 2. Management's Discussion and Analysis</b>
    Some MD&A text.
    </body></html>
    """
    notes = []
    result = extract_10q_sections(html, notes)
    assert "item1" in result and "item2" in result
    assert "Revenue" in result["item1"]
    assert "MD&A" in result["item2"]
    assert isinstance(result["item1_tables"], list)

# Unit test for fetch_10q with monkeypatching
@pytest.mark.usefixtures("monkeypatch")
def test_fetch_10q_mock(monkeypatch):
    # Mock fetch_10q_html to return a simple HTML
    monkeypatch.setattr("app.api.agents.agent1_fetch_sec.fetch_10q_html", lambda url: "<html><body>Item 1. Financial Statements Item 2. MD&A</body></html>")
    # Mock get_quarterly_filings to return a fake filing
    monkeypatch.setattr("app.api.agents.agent1_fetch_sec.get_quarterly_filings", lambda request, company_name, count: {
        "company_name": "TestCo",
        "cik": "123",
        "filings": [{
            "filing_date": "2024-01-01",
            "html_url": "dummy_url",
            "title": "TestCo Q1",
            "marker": "📌 Most Recent"
        }]
    })
    result = fetch_10q("TestCo")
    filing = result["filings"][0]
    extracted = filing["extracted_sections"]
    assert "item1" in extracted and "item2" in extracted
    