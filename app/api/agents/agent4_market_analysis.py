from app.api.groq_client import call_groq

def analyze_market(company_name: str, meeting_context: str) -> dict:
    """
    Agent 4: Analyze the market and competitive landscape for a given company and context.
    """
    try:
        prompt = build_market_prompt(company_name, meeting_context)
        result = call_groq(prompt)
        print("Agent 4 Groq raw output:", result)
        parsed_analysis = parse_groq_response(result)
        return parsed_analysis
    except Exception as e:
        return {"error": f"Agent 4 - Market analysis failed: {str(e)}"}


def build_market_prompt(company: str, context: str) -> str:
    """
    Build a prompt for Groq to perform market and competitive analysis,
    using baseline questions and dynamic context-driven hints.
    """
    lc_context = context.lower()
    dynamic_hint = ""

    if "security" in lc_context or "cyber" in lc_context:
        dynamic_hint = '- "What are your top 1–2 cyber resilience priorities now and going into next year?"'
    elif "technology" in lc_context or "innovation" in lc_context:
        dynamic_hint = '- "Where are you investing most aggressively in tech-enabled transformation?"'
    elif "technical debt" in lc_context:
        dynamic_hint = '- "What’s your current strategy for managing or paying down technical debt?"'
    elif "managed service" in lc_context or "msp" in lc_context:
        dynamic_hint = '- "Which managed services are you considering now and why?"'
    elif "hybrid cloud" in lc_context or "multi-cloud" in lc_context:
        dynamic_hint = '- "How are you balancing on-prem and public cloud workloads today?"'

    additional_hint = f"\n**Additional example based on this specific meeting context:**\n{dynamic_hint}" if dynamic_hint else ""

    prompt = f"""
You are a market analyst...

Given the company "{company}" and the following meeting context: "{context}",
analyze the market and competitive landscape.

Provide:
- A list of 2-3 major competitors and their positioning
- Key opportunities in the industry
- Key risks or threats affecting the company
- Any macroeconomic factors relevant
- Smart, context-specific questions that an executive could ask during the meeting

Respond in the following strict JSON format:

{{
    "opportunities": [],
    "threats": [],
    "competitive_landscape": [
        {{"competitor": "", "positioning": ""}},
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
{additional_hint}
"""
    return prompt

def parse_groq_response(response: dict) -> dict:
    try:
        content = response["content"]
        return json.loads(content) if isinstance(content, str) else content
    except Exception as e:
        return {"error": f"Invalid response from Groq during market analysis: {str(e)}"}
