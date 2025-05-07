from app.api.prompt_builder import build_agent_1_prompt
from app.api.memory_schema import Agent2Financials, Agent3Profile, Agent4RiskMap

def test_prompt_builder_basic():
    agent2 = Agent2Financials(
        financial_summary="Summary",
        key_metrics_table={"Revenue": ["$1M"]},
        recent_events_summary="Event",
        questions_to_ask=["Q1"]
    )
    agent3 = Agent3Profile(name="Jane", signals=["Signal"])
    agent4 = Agent4RiskMap(
        threats=["Threat"], opportunities=["Opp"], competitive_landscape=[], macroeconomic_factors=[], questions_to_ask=[]
    )
    prompt = build_agent_1_prompt(agent2, agent3, agent4)
    assert "Summary" in prompt
    assert "Jane" in prompt
    assert "Threat" in prompt
    assert "Q1" in prompt

def test_prompt_builder_with_missing_optional():
    agent2 = Agent2Financials(
        financial_summary="Summary",
        key_metrics_table={},
        recent_events_summary="Event",
        questions_to_ask=[]
    )
    agent3 = Agent3Profile(name="Jane", signals=[])
    agent4 = Agent4RiskMap(
        threats=[], opportunities=[], competitive_landscape=[], macroeconomic_factors=[], questions_to_ask=[]
    )
    prompt = build_agent_1_prompt(agent2, agent3, agent4)
    assert "Summary" in prompt
    assert "Jane" in prompt 