from app.api.memory_schema import Agent2Financials, Agent3Profile, Agent4RiskMap
from typing import List, Optional

def format_table(table_dict):
    if not table_dict:
        return "No data available."
    # If table_dict is already a markdown string, just return it
    if isinstance(table_dict, str):
        return table_dict
    quarters = list(table_dict.keys())
    metrics = set()
    for q in quarters:
        if isinstance(table_dict[q], dict):
            metrics.update(table_dict[q].keys())
        elif isinstance(table_dict[q], list):
            for item in table_dict[q]:
                if ":" in item:
                    metrics.add(item.split(":")[0].strip())
    metrics = sorted(metrics)
    header = "| Metric | " + " | ".join(quarters) + " |\n"
    sep = "|---" * (len(quarters)+1) + "|\n"
    rows = ""
    for m in metrics:
        row = f"| {m} | "
        for q in quarters:
            val = ""
            if isinstance(table_dict[q], dict):
                val = table_dict[q].get(m, "")
            elif isinstance(table_dict[q], list):
                for item in table_dict[q]:
                    if item.startswith(f"{m}:"):
                        val = item.split(":", 1)[1].strip()
            row += f"{val} | "
        rows += row + "\n"
    return header + sep + rows

def build_agent_1_prompt(agent_2_data: Agent2Financials, agent_3_data: Agent3Profile, agent_4_data: Agent4RiskMap, additional_context: Optional[dict] = None, is_public: bool = True, private_company_analysis: Optional[dict] = None, enforce_title: bool = False) -> str:
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
    private_section = ""
    if not is_public:
        private_section = (
            "This company appears to be private. No SEC filings or public financials are available.\n"
            "Analysis is based on public web signals and industry data.\n\n"
            f"Private Company Analysis:\n{private_company_analysis if private_company_analysis else 'No additional data found.'}\n\n"
        )
    title_instruction = ""
    if enforce_title and agent_3_data.title:
        title_instruction = f"\nDo not change or infer a different title for the contact. Use only the title provided above: {agent_3_data.title}.\n"
    return (
        "You are an executive assistant AI tasked with synthesizing intelligence from three specialized agents. Your job is to produce a sharp, structured briefing.\n\n"
        f"{context_section}"
        f"{private_section}"
        "### Agent 2: Financial Overview ###\n"
        f"Summary:\n{agent_2_data.financial_summary}\n\n"
        f"Key Metrics Table (render as markdown):\n{format_table(agent_2_data.key_metrics_table)}\n\n"
        f"Events:\n{agent_2_data.recent_events_summary}\n\n"
        f"Questions:\n- {agent2_questions}\n\n"
        "### Agent 3: Executive Profile ###\n"
        f"Name: {agent_3_data.name}\n"
        f"Title: {agent_3_data.title or 'Not specified'}\n"
        f"{title_instruction}"
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