from app.api.memory_schema import Agent2Financials, Agent3Profile, Agent4RiskMap
from typing import List, Optional

def build_agent_1_prompt(agent_2_data: Agent2Financials, agent_3_data: Agent3Profile, agent_4_data: Agent4RiskMap, additional_context: Optional[dict] = None) -> str:
    # Avoid backslashes in f-string expressions by building the string in parts
    agent2_questions = "\n- ".join(agent_2_data.questions_to_ask)
    agent3_signals = "\n- ".join(agent_3_data.signals)
    agent4_threats = "\n- ".join(agent_4_data.threats)
    agent4_opportunities = "\n- ".join(agent_4_data.opportunities)
    agent4_macro = "\n- ".join(agent_4_data.macroeconomic_factors)
    agent4_questions = "\n- ".join(agent_4_data.questions_to_ask)
    # Summarize additional context
    ac = additional_context or {}
    context_section = (
        "Additional context from user (pre-meeting):\n"
        f"- First meeting: {ac.get('first_meeting', 'Not specified')}\n"
        f"- User knowledge: {ac.get('user_knowledge', 'Not specified')}\n"
        f"- Proposed solutions: {ac.get('proposed_solutions', 'Not specified')}\n"
        f"- Wants messaging help: {ac.get('messaging_help', 'Not specified')}\n\n"
    )
    return (
        "You are an executive assistant AI tasked with synthesizing intelligence from three specialized agents. Your job is to produce a sharp, structured briefing.\n\n"
        f"{context_section}"
        "### Agent 2: Financial Overview ###\n"
        f"Summary:\n{agent_2_data.financial_summary}\n\n"
        f"Key Metrics Table:\n{agent_2_data.key_metrics_table}\n\n"
        f"Events:\n{agent_2_data.recent_events_summary}\n\n"
        f"Questions:\n- {agent2_questions}\n\n"
        "### Agent 3: Executive Profile ###\n"
        f"Name: {agent_3_data.name}\n"
        f"Title: {agent_3_data.title or 'Not specified'}\n"
        f"Signals:\n- {agent3_signals}\n"
        f"Engagement Style: {agent_3_data.engagement_style or 'Not specified'}\n\n"
        "### Agent 4: Market, Risk, and Opportunity ###\n"
        f"Threats:\n- {agent4_threats}\n\n"
        f"Opportunities:\n- {agent4_opportunities}\n\n"
        f"Competitors:\n{agent_4_data.competitive_landscape}\n\n"
        f"Macroeconomic Factors:\n- {agent4_macro}\n\n"
        f"Strategic Questions:\n- {agent4_questions}\n\n"
        "### Your Task ###\n"
        "Synthesize this into a meeting prepation document for your stakeholder. \n"
        "Highlight: the information you have gathered, and the engagement questions you have prepared.\n"
        "Make it sharp, confident, and data-backed.\n"
        "Be ready for follow-up questions and to make adjustments based on the conversation.\n"
        "Your goal is to be helpful and informative, and to leave the stakeholder feeling confident and prepared.\n"
    ) 