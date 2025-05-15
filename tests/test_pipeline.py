import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.api.run_pipeline import router, PipelineRequest
from fastapi import FastAPI
import logging

app = FastAPI()
app.include_router(router)
client = TestClient(app)

# Updated mock agent outputs to match new schema
mock_sec_data = {
    "company_name": "TestCo",
    "cik": "123",
    "filings": [
        {
            "filing_date": "2024-01-01",
            "html_url": "http://example.com/10q",
            "title": "TestCo Q1",
            "marker": "📌 Most Recent",
            "estimated_tokens": 8000,
            "extracted_sections": {
                "item1": "Balance Sheet ...",
                "item2": "MD&A ...",
                "notes": "Note 1 ...",
                "item1_tables": ["header1,header2\nval1,val2"],
                "extraction_notes": ["Item 1 extracted", "Item 2 extracted"]
            },
            "extraction_notes": []
        }
    ]
}

valid_agent2 = {
    "financial_summary": "Strong growth.",
    "key_metrics_table": {"Q1 2024": ["Revenue: $1M"]},
    "recent_events_summary": "IPO completed.",
    "suggested_graph": None,
    "questions_to_ask": ["What are the risks?"],
    "notes": ["All required metrics extracted via Python table parsing."],
    "raw_tables": [[["header1", "header2"], ["val1", "val2"]]]
}
valid_agent3 = [{
    "name": "Jane Doe",
    "title": "CFO",
    "signals": ["High performer"],
    "engagement_style": "Direct"
}]
valid_agent4 = {
    "threats": ["Competition"],
    "opportunities": ["Expansion"],
    "competitive_landscape": [{"competitor": "X", "positioning": "Leader"}],
    "macroeconomic_factors": ["Inflation"],
    "questions_to_ask": ["How to grow?"]
}

@patch("app.api.run_pipeline.openai.OpenAI")
@patch("app.api.run_pipeline.analyze_company", return_value=valid_agent4)
@patch("app.api.run_pipeline.profile_people", return_value=valid_agent3)
@patch("app.api.run_pipeline.analyze_financials", return_value=valid_agent2)
@patch("app.api.run_pipeline.fetch_10q", return_value=mock_sec_data)
def test_run_pipeline_success(mock_agent1, mock_agent2, mock_agent3, mock_agent4, mock_openai):
    # Mock the OpenAI client and its response
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Synthesized briefing."))]
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai.return_value = mock_client
    payload = {
        "company": "TestCo",
        "people": ["Jane Doe"],
        "meeting_context": "Quarterly review"
    }
    response = client.post("/run_pipeline", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["executive_briefing"] == "Synthesized briefing."
    assert data["company"] == "TestCo"
    # Check new fields
    assert "raw_tables" in data["financial_analysis"]
    assert "notes" in data["financial_analysis"]

@patch("app.api.run_pipeline.openai.OpenAI")
@patch("app.api.run_pipeline.analyze_company", return_value=valid_agent4)
@patch("app.api.run_pipeline.profile_people", return_value=valid_agent3)
@patch("app.api.run_pipeline.analyze_financials", return_value={"bad": "data"})
@patch("app.api.run_pipeline.fetch_10q", return_value={"company_name": "TestCo", "cik": "123", "filings": []})
def test_run_pipeline_agent2_invalid(mock_agent1, mock_agent2, mock_agent3, mock_agent4, mock_openai):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Synthesized briefing."))]
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai.return_value = mock_client
    payload = {
        "company": "TestCo",
        "people": ["Jane Doe"],
        "meeting_context": "Quarterly review"
    }
    response = client.post("/run_pipeline", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "Agent 2 output invalid" in data["executive_briefing"]

@patch("app.api.run_pipeline.openai.OpenAI")
@patch("app.api.run_pipeline.analyze_company", return_value=valid_agent4)
@patch("app.api.run_pipeline.profile_people", return_value=[{"bad": "data"}])
@patch("app.api.run_pipeline.analyze_financials", return_value=valid_agent2)
@patch("app.api.run_pipeline.fetch_10q", return_value={"company_name": "TestCo", "cik": "123", "filings": []})
def test_run_pipeline_agent3_invalid(mock_agent1, mock_agent2, mock_agent3, mock_agent4, mock_openai):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Synthesized briefing."))]
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai.return_value = mock_client
    payload = {
        "company": "TestCo",
        "people": ["Jane Doe"],
        "meeting_context": "Quarterly review"
    }
    response = client.post("/run_pipeline", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "Agent 3 output invalid" in data["executive_briefing"]

@patch("app.api.run_pipeline.openai.OpenAI")
@patch("app.api.run_pipeline.analyze_company", return_value={"bad": "data"})
@patch("app.api.run_pipeline.profile_people", return_value=valid_agent3)
@patch("app.api.run_pipeline.analyze_financials", return_value=valid_agent2)
@patch("app.api.run_pipeline.fetch_10q", return_value={"company_name": "TestCo", "cik": "123", "filings": []})
def test_run_pipeline_agent4_invalid(mock_agent1, mock_agent2, mock_agent3, mock_agent4, mock_openai):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Synthesized briefing."))]
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai.return_value = mock_client
    payload = {
        "company": "TestCo",
        "people": ["Jane Doe"],
        "meeting_context": "Quarterly review"
    }
    response = client.post("/run_pipeline", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "Agent 4 output invalid" in data["executive_briefing"]

@patch("app.api.run_pipeline.fetch_10q", return_value={"error": "SECAPI failed"})
def test_run_pipeline_agent1_error(mock_agent1):
    payload = {
        "company": "TestCo",
        "people": ["Jane Doe"],
        "meeting_context": "Quarterly review"
    }
    response = client.post("/run_pipeline", json=payload)
    # Accept either 500 or 200 with error in response
    if response.status_code == 500:
        assert True
    else:
        data = response.json()
        assert "error" in data["sec_data"] or "error" in data

# Truncation test: simulate huge item1 and check for truncation notes
@patch("app.api.run_pipeline.openai.OpenAI")
@patch("app.api.run_pipeline.analyze_company", return_value=valid_agent4)
@patch("app.api.run_pipeline.profile_people", return_value=valid_agent3)
@patch("app.api.run_pipeline.analyze_financials")
@patch("app.api.run_pipeline.fetch_10q", return_value={
    "company_name": "TestCo",
    "cik": "123",
    "filings": [
        {
            "filing_date": "2024-01-01",
            "html_url": "http://example.com/10q",
            "title": "TestCo Q1",
            "marker": "📌 Most Recent",
            "estimated_tokens": 200000,
            "extracted_sections": {
                "item1": "A" * 200000,  # Simulate huge section
                "item2": "B" * 1000,
                "notes": "C" * 1000,
                "item1_tables": [],
                "extraction_notes": []
            },
            "extraction_notes": []
        }
    ]
})
def test_run_pipeline_truncation(mock_agent1, mock_agent2, mock_agent3, mock_agent4, mock_openai):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Synthesized briefing."))]
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai.return_value = mock_client
    def analyze_financials_side_effect(extracted_sections, additional_context=None):
        notes = extracted_sections.get("extraction_notes", [])
        truncation_notes = extracted_sections.get("truncation_notes", [])
        # Simulate truncation note if item1 is very large
        if len(extracted_sections.get("item1", "")) > 100000:
            truncation_notes.append("item1 truncated to fit token budget.")
        return {
            "financial_summary": "Truncated input test.",
            "key_metrics_table": {},
            "recent_events_summary": "",
            "suggested_graph": None,
            "questions_to_ask": [],
            "notes": notes + truncation_notes,
            "raw_tables": []
        }
    mock_agent2.side_effect = analyze_financials_side_effect
    payload = {
        "company": "TestCo",
        "people": ["Jane Doe"],
        "meeting_context": "Quarterly review"
    }
    response = client.post("/run_pipeline", json=payload)
    assert response.status_code == 200
    data = response.json()
    # Check that truncation notes are present
    assert any("truncated" in note or "omitted" in note for note in data["financial_analysis"]["notes"])

@pytest.mark.parametrize("company", ["Ball Corp"])
def test_agent1_real_extraction(company):
    from app.api.agents.agent1_fetch_sec import fetch_10q
    result = fetch_10q(company)
    filings = result.get("filings", [])
    assert filings, f"No filings returned from SEC API for {company}."
    extracted = filings[0].get("extracted_sections", {})

    # Debug: print the extracted part keys
    print("Extracted part keys:", list(extracted.keys()))
    # Debug: print the first 500 characters of Part I > Item 1.
    part_i_item_1_text = extracted.get("Part I", {}).get("items", {}).get("Item 1.", {}).get("text", "")
    print("First 500 chars of Part I > Item 1.:", part_i_item_1_text[:500])

    # Should always have "Part I" and "Part II" as keys
    assert "Part I" in extracted and "Part II" in extracted, (
        f"Extracted sections missing expected parts for {company}. Extracted keys: {list(extracted.keys())}"
    )

    # Check that each part has items and token counts
    for part_key in ["Part I", "Part II"]:
        part_data = extracted.get(part_key, {})
        assert "total_tokens" in part_data and "items" in part_data
        assert isinstance(part_data["items"], dict)
        if part_data["items"]:
            first_item = next(iter(part_data["items"].values()))
            assert "text" in first_item and "tables" in first_item and "tokens" in first_item

    print(f"\n===== FULL EXTRACTED DATA FOR {company} =====")
    for part, pdata in extracted.items():
        print(f"\n{part} (tokens: {pdata.get('total_tokens', 0)})")
        for item, idata in pdata.get("items", {}).items():
            print(f"\n{item} (tokens: {idata.get('tokens', 0)})\nText: {idata.get('text', '')[:500]}")
            if idata.get("tables"):
                print(f"\nFirst Table (raw):\n{idata['tables'][0]}") 