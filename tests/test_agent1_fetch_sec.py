import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from app.api.agents.agent1_fetch_sec import extract_10q_sections, fetch_10q

# Unit test for extract_10q_sections
def test_extract_10q_sections_parts_and_items():
    html = """
    <html><body>
    <b>PART 1</b>
    <b>Item 1.</b>
    <table><tr><td>Revenue</td><td>100</td></tr></table>
    <b>Item 2.</b>
    Some MD&A text.
    <b>Part II</b>
    <b>Item 1.</b>
    Legal proceedings.
    </body></html>
    """
    notes = []
    result = extract_10q_sections(html, notes)
    # Should always have "Part I" and "Part II" as keys
    assert "Part I" in result and "Part II" in result
    # Check for items in Part I
    part1 = result["Part I"]
    assert "items" in part1 and "Item 1." in part1["items"] and "Item 2." in part1["items"]
    # Check for items in Part II
    part2 = result["Part II"]
    assert "items" in part2 and "Item 1." in part2["items"]
    # Check for text, tables, and tokens in an item
    item1 = part1["items"]["Item 1."]
    assert "text" in item1 and "tables" in item1 and "tokens" in item1
    assert "Revenue" in item1["text"] or any("Revenue" in t for t in item1["tables"])
    assert isinstance(item1["tokens"], int)
    print("Extracted structure:", result)

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
    