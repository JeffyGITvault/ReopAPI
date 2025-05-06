import logging
import json
from typing import Dict, Any
from app.api.groq_client import call_groq

logger = logging.getLogger(__name__)

def analyze_company(company_name: str, meeting_context: str) -> Dict[str, Any]:
    """
    Agent 4: Analyze the competitive landscape for a given company and add meeting context.
    Returns a dict with market analysis or error.
    """
    try:
        prompt = build_market_prompt(company_name, meeting_context)
        result = call_groq(prompt)
        logger.info("Agent 4 Groq raw output: %s", result)
        parsed_analysis = parse_groq_response(result)
        return parsed_analysis
    except Exception as e:
        logger.error(f"Agent 4 - analyze company failed: {e}")
        return {"error": f"Agent 4 - analyze company failed: {str(e)}"}


def build_market_prompt(company: str, context: str) -> str:
    """
    Build a prompt for Groq to perform company analysis with meeting context,
    using baseline questions and dynamic context-driven hints.
    """
    lc_context = context.lower()
    dynamic_hint = ""

    if "security" in lc_context or "cyber" in lc_context:
        dynamic_hint = '- "What are your top 1–2 cyber resilience priorities now and going into next year?"'
    elif "technology" in lc_context or "innovation" in lc_context:
        dynamic_hint = '- "Where are you investing most aggressively in tech-enabled transformation?"'
    elif "technical debt" in lc_context:
        dynamic_hint = '- "What\'s your current strategy for managing or paying down technical debt?"'
    elif "managed service" in lc_context or "msp" in lc_context:
        dynamic_hint = '- "Which managed services are you considering now and why?"'
    elif "hybrid cloud" in lc_context or "multi-cloud" in lc_context:
        dynamic_hint = '- "How are you balancing on-prem and public cloud workloads today?"'

    additional_hint = f"\n**Additional example based on this specific meeting context:**\n{dynamic_hint}" if dynamic_hint else ""

    system_message = (
        "You are a company and meeting context preparation analyst. Your job is to analyze the company competitive landscape, and macroeconomic factors for the given company and meeting context. "
        "You must extract and cite specific competitors based on the provided context and any available financial analysis. "
        "Respond ONLY in the following strict JSON format. Do not add any extra text or commentary."
    )

    prompt = f"""
You are a market analyst...

Given the company \"{company}\" and the following meeting context: \"{context}\",
analyze the market and competitive landscape.

Provide:
- A list of 2-3 major competitors for the given company and their positioning versus the company
- Key risks or threats affecting the company based on the financial analysis you conducted
- Any macroeconomic factors relevant to the company
- Smart, context-specific questions to ask during the meeting based on the meeting context

Respond in the following strict JSON format:

{{
    "opportunities": [],
    "threats": [],
    "competitive_landscape": [
        {{"competitor": "", "positioning": ""}}
    ],
    "macroeconomic_factors": [],
    "questions_to_ask": []
}}

**Baseline questions to guide your thinking:**
- "What contingency plans are in place if you have a security compromise in your supply chain?"
- "How are you prioritizing technology and security investments versus operational cost control in the next 12 months?"
- "What current cyber resilience strategies do you have in place today and what would you like to improve in the next 6-12 months?"
- "How does the organization manage technical debt and how much technical debt do you have impacting your resilience?"
- "How does the organization utilize managed services to address skills and talent gaps?"
{additional_hint}

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
