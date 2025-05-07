import pytest
from app.api.memory_schema import Agent2Financials, Agent3Profile, Agent4RiskMap

def test_agent2financials_valid():
    data = {
        "financial_summary": "Summary",
        "key_metrics_table": {"Revenue": ["$1M"]},
        "recent_events_summary": "Event",
        "questions_to_ask": ["Q1"]
    }
    model = Agent2Financials(**data)
    assert model.financial_summary == "Summary"
    assert model.key_metrics_table["Revenue"] == ["$1M"]

def test_agent2financials_missing_required():
    with pytest.raises(Exception):
        Agent2Financials(key_metrics_table={}, recent_events_summary="", questions_to_ask=[])

def test_agent3profile_valid():
    data = {"name": "Jane", "signals": ["Signal"]}
    model = Agent3Profile(**data)
    assert model.name == "Jane"
    assert model.signals == ["Signal"]

def test_agent3profile_missing_required():
    with pytest.raises(Exception):
        Agent3Profile(signals=["Signal"])

def test_agent4riskmap_valid():
    data = {
        "threats": ["Threat"],
        "opportunities": ["Opp"],
        "competitive_landscape": [],
        "macroeconomic_factors": [],
        "questions_to_ask": []
    }
    model = Agent4RiskMap(**data)
    assert model.threats == ["Threat"]

def test_agent4riskmap_missing_required():
    with pytest.raises(Exception):
        Agent4RiskMap(opportunities=[], competitive_landscape=[], macroeconomic_factors=[], questions_to_ask=[]) 