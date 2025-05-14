import pytest
from app.api.agents.agent2_analyze_financials import analyze_financials

def test_analyze_financials_python_extraction():
    extracted_sections = {
        "item1": "Revenue, Net Income",
        "item2": "MD&A text",
        "notes": "Note 1",
        "item1_tables": ["Revenue,Net Income\n100,10"],
        "extraction_notes": []
    }
    result = analyze_financials(extracted_sections)
    assert "financial_summary" in result
    assert "key_metrics_table" in result
    assert "raw_tables" in result

# Test fallback/LLM path (simulate missing tables/metrics)
def test_analyze_financials_llm_fallback(monkeypatch):
    # Patch call_groq to return a valid JSON string
    monkeypatch.setattr("app.api.agents.agent2_analyze_financials.call_groq", lambda *a, **kw: '{"financial_summary": "LLM fallback", "key_metrics_table": {}, "recent_events_summary": "", "suggested_graph": "", "questions_to_ask": []}')
    extracted_sections = {
        "item1": "",
        "item2": "Some MD&A text",
        "notes": "",
        "item1_tables": [],
        "extraction_notes": []
    }
    result = analyze_financials(extracted_sections)
    assert "financial_summary" in result
    assert result["financial_summary"] == "LLM fallback" 