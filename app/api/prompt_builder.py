from app.api.memory_schema import Agent2Financials, Agent3Profile, Agent4RiskMap
from typing import List

def build_agent_1_prompt(agent_2_data: Agent2Financials, agent_3_data: Agent3Profile, agent_4_data: Agent4RiskMap) -> str:
    return f"""
You are an executive assistant AI tasked with synthesizing intelligence from three specialized agents. Your job is to produce a sharp, structured briefing.

### Agent 2: Financial Overview ###
Summary:
{agent_2_data.financial_summary}

Key Metrics Table:
{agent_2_data.key_metrics_table}

Events:
{agent_2_data.recent_events_summary}

Questions:
- {'\n- '.join(agent_2_data.questions_to_ask)}

### Agent 3: Executive Profile ###
Name: {agent_3_data.name}
Title: {agent_3_data.title or 'Not specified'}
Signals:
- {'\n- '.join(agent_3_data.signals)}
Engagement Style: {agent_3_data.engagement_style or 'Not specified'}

### Agent 4: Market, Risk, and Opportunity ###
Threats:
- {'\n- '.join(agent_4_data.threats)}

Opportunities:
- {'\n- '.join(agent_4_data.opportunities)}

Competitors:
{agent_4_data.competitive_landscape}

Macroeconomic Factors:
- {'\n- '.join(agent_4_data.macroeconomic_factors)}

Strategic Questions:
- {'\n- '.join(agent_4_data.questions_to_ask)}

### Your Task ###
Synthesize this into a meeting prepation document for your stakeholder. 
Highlight: the information you have gathered, and the engagement questions you have prepared.
Make it sharp, confident, and data-backed.
Be ready for follow-up questions and to make adjustments based on the conversation.
Your goal is to be helpful and informative, and to leave the stakeholder feeling confident and prepared.
""" 