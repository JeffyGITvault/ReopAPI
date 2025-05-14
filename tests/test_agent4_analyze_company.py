import pytest
from app.api.agents.agent4_analyze_company import build_market_prompt, parse_groq_response

def test_build_market_prompt_basic():
    prompt = build_market_prompt("TestCo", "cloud strategy")
    assert "TestCo" in prompt
    assert "cloud strategy" in prompt

def test_parse_groq_response_valid_json():
    response = '{"opportunities": [], "threats": [], "competitive_landscape_table": "", "industry_trends": [], "regulatory_changes": [], "macroeconomic_factors": [], "questions_to_ask": [], "citations": []}'
    result = parse_groq_response(response)
    assert isinstance(result, dict)
    assert "opportunities" in result 