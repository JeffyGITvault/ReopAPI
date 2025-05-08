import logging
import json
from typing import Dict, Any
from app.api.groq_client import call_groq

logger = logging.getLogger(__name__)

def analyze_company(company_name: str, meeting_context: str, agent2_summary: str = None, agent3_profile: dict = None) -> Dict[str, Any]:
    """
    Agent 4: Analyze the market and competitive landscape for a given company and context.
    Returns a dict with market analysis or error.
    """
    try:
        prompt = build_market_prompt(company_name, meeting_context, agent2_summary, agent3_profile)
        result = call_groq(prompt, max_tokens=32768)
        logger.info("Agent 4 Groq raw output: %s", result)
        parsed_analysis = parse_groq_response(result)
        return parsed_analysis
    except Exception as e:
        logger.error(f"Agent 4 - Market analysis failed: {e}")
        return {"error": f"Agent 4 - Market analysis failed: {str(e)}"}


def build_market_prompt(company: str, context: str, agent2_summary: str = None, agent3_profile: dict = None) -> str:
    """
    Build a prompt for Groq to perform market and competitive analysis,
    using baseline questions and dynamic context-driven hints.
    Now supports multiple context-specific hints and leverages agent2/agent3 outputs.
    """
    lc_context = context.lower()
    dynamic_hints = []
    # Keyword-based
    if "security" in lc_context or "cyber" in lc_context:
        dynamic_hints.append('What are your top 1–2 cyber resilience priorities now and going into next year?')
    if "technology" in lc_context or "innovation" in lc_context:
        dynamic_hints.append('Where are you investing most aggressively in tech-enabled transformation?')
    if "technical debt" in lc_context:
        dynamic_hints.append("What's your current strategy for managing or paying down technical debt?")
    if "managed service" in lc_context or "msp" in lc_context:
        dynamic_hints.append("Which managed services are you considering now and why?")
    if "hybrid cloud" in lc_context or "multi-cloud" in lc_context:
        dynamic_hints.append("How are you balancing on-prem and public cloud workloads today?")
    # Agent 2-based
    if agent2_summary and "margin" in agent2_summary.lower():
        dynamic_hints.append("How are you addressing margin pressure in your business?")
    # Agent 3-based
    if agent3_profile and agent3_profile.get("title", "").lower() == "ciso":
        dynamic_hints.append("What are your top security investment priorities for the next 12 months?")
    # ...add more as needed...
    if dynamic_hints:
        additional_hint = "\n**Additional context-specific questions:**\n" + "\n".join(f"- {q}" for q in dynamic_hints)
    else:
        additional_hint = ""

    system_message = (
        "You are a market and competitive intelligence analyst. Your job is to analyze the market, competitive landscape, and macroeconomic factors for the given company and meeting context. "
        "You must ground your analysis in recent news, SEC filings, and industry reports if available. "
        "Cite sources (URLs or news titles) where possible. "
        "Structure the competitor analysis as a markdown table with columns: Competitor, Positioning, Key Differentiators. "
        "Explicitly call out industry trends and regulatory changes. "
        "Tie risks and opportunities directly to the meeting context and recent company events. "
        "Respond ONLY in the following strict JSON format. Do not add any extra text or commentary."
    )

    prompt = f"""
You are a market analyst...

Given the company \"{company}\" and the following meeting context: \"{context}\",
analyze the market and competitive landscape.

Instructions:
- Use recent news, SEC filings, and industry reports to ground your analysis. If you cannot find relevant data, state that explicitly.
- Structure the competitor analysis as a markdown table with columns: Competitor, Positioning, Key Differentiators.
- Call out industry trends and regulatory changes that may impact the company.
- Tie risks and opportunities directly to the meeting context and recent company events.
- Cite sources (URLs or news titles) where possible.
- Keep all output in strict JSON, but allow markdown tables in string fields.
{additional_hint}

Respond in the following strict JSON format:
{{
    "opportunities": [],
    "threats": [],
    "competitive_landscape_table": "",
    "industry_trends": [],
    "regulatory_changes": [],
    "macroeconomic_factors": [],
    "questions_to_ask": [],
    "citations": []
}}

**Baseline questions to guide your thinking:**
- "What contingency plans are in place if you have a security compromise in your supply chain?"
- "How are you prioritizing technology and security investments versus operational cost control in the next 12 months?"
- "What current cyber resilience strategies do you have in place today and what would you like to improve in the next 6-12 months?"
- "How does the organization manage technical debt and how much technical debt do you have impacting your resilience?"
- "How does the organization utilize managed services to address skills and talent gaps?"

{system_message}
"""
    return prompt

def parse_groq_response(response: Any) -> Dict[str, Any]:
    """
    Parse the response from Groq, handling both string and dict input.
    """
    try:
        content = response["content"] if isinstance(response, dict) and "content" in response else response
        return json.loads(content) if isinstance(content, str) else response
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON returned from Groq: {e}")
        return {"error": f"Invalid JSON returned from Groq: {str(e)}"}
    except Exception as e:
        logger.error(f"Failed to parse Groq response: {e}")
        return {"error": f"Failed to parse Groq response: {str(e)}"}
