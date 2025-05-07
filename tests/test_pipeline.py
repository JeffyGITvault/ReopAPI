import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.api.run_pipeline import router, PipelineRequest
from fastapi import FastAPI

app = FastAPI()
app.include_router(router)
client = TestClient(app)

# Mock agent outputs
valid_agent2 = {
    "financial_summary": "Strong growth.",
    "key_metrics_table": {"Revenue": ["$1M", "$2M"]},
    "recent_events_summary": "IPO completed.",
    "suggested_graph": None,
    "questions_to_ask": ["What are the risks?"]
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

@patch("app.api.run_pipeline.fetch_10q", return_value={"company_name": "TestCo", "cik": "123", "filings": []})
@patch("app.api.run_pipeline.analyze_financials", return_value=valid_agent2)
@patch("app.api.run_pipeline.profile_people", return_value=valid_agent3)
@patch("app.api.run_pipeline.analyze_company", return_value=valid_agent4)
@patch("app.api.run_pipeline.openai.ChatCompletion.create", return_value={"choices": [{"message": {"content": "Synthesized briefing."}}]})
def test_run_pipeline_success(mock_openai, mock_agent4, mock_agent3, mock_agent2, mock_agent1):
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

@patch("app.api.run_pipeline.fetch_10q", return_value={"company_name": "TestCo", "cik": "123", "filings": []})
@patch("app.api.run_pipeline.analyze_financials", return_value={"bad": "data"})
@patch("app.api.run_pipeline.profile_people", return_value=valid_agent3)
@patch("app.api.run_pipeline.analyze_company", return_value=valid_agent4)
@patch("app.api.run_pipeline.openai.ChatCompletion.create", return_value={"choices": [{"message": {"content": "Synthesized briefing."}}]})
def test_run_pipeline_agent2_invalid(mock_openai, mock_agent4, mock_agent3, mock_agent2, mock_agent1):
    payload = {
        "company": "TestCo",
        "people": ["Jane Doe"],
        "meeting_context": "Quarterly review"
    }
    response = client.post("/run_pipeline", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "Agent 2 output invalid" in data["executive_briefing"]

@patch("app.api.run_pipeline.fetch_10q", return_value={"company_name": "TestCo", "cik": "123", "filings": []})
@patch("app.api.run_pipeline.analyze_financials", return_value=valid_agent2)
@patch("app.api.run_pipeline.profile_people", return_value=[{"bad": "data"}])
@patch("app.api.run_pipeline.analyze_company", return_value=valid_agent4)
@patch("app.api.run_pipeline.openai.ChatCompletion.create", return_value={"choices": [{"message": {"content": "Synthesized briefing."}}]})
def test_run_pipeline_agent3_invalid(mock_openai, mock_agent4, mock_agent3, mock_agent2, mock_agent1):
    payload = {
        "company": "TestCo",
        "people": ["Jane Doe"],
        "meeting_context": "Quarterly review"
    }
    response = client.post("/run_pipeline", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "Agent 3 output invalid" in data["executive_briefing"]

@patch("app.api.run_pipeline.fetch_10q", return_value={"company_name": "TestCo", "cik": "123", "filings": []})
@patch("app.api.run_pipeline.analyze_financials", return_value=valid_agent2)
@patch("app.api.run_pipeline.profile_people", return_value=valid_agent3)
@patch("app.api.run_pipeline.analyze_company", return_value={"bad": "data"})
@patch("app.api.run_pipeline.openai.ChatCompletion.create", return_value={"choices": [{"message": {"content": "Synthesized briefing."}}]})
def test_run_pipeline_agent4_invalid(mock_openai, mock_agent4, mock_agent3, mock_agent2, mock_agent1):
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
    assert response.status_code == 500
    assert "Agent 1 failed" in response.text 