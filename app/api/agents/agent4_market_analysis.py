# app/api/agents/agent4_market_analysis.py

from app.api.groq_client import call_groq

def analyze_market(company_name: str, meeting_context: str) -> dict:
    """
    Agent 4: Analyze the market and competitive landscape for a given company and context.
    """
    try:
        prompt = build_market_prompt(company_name, meeting_context)

        result = call_groq(prompt)

        parsed_analysis = parse_groq_response(result)

        return parsed_analysis

    except Exception as e:
        return {"error": f"Agent 4 - Market analysis failed: {str(e)}"}

def build_market_prompt(company: str, context: str) -> str:
    """
    Build a prompt for Groq to perform market and competitive analysis.
    """
    prompt = f"""
You are a market analyst.

Given the company "{company}" and the following meeting context: "{context}",
analyze the market and competitive landscape.

Provide:
- A list of 2-3 major competitors and their positioning
- Key opportunities in the industry
- Key risks or threats affecting the company
- Any macroeconomic factors relevant
- smart, context-specific questions that an executive could ask during the meeting

Respond in the following strict JSON format:

{{
    "opportunities": [],
    "threats": [],
    "competitive_landscape": [
        {{"competitor": "", "positioning": ""}},
        {{"competitor": "", "positioning": ""}}
    ],
    "macroeconomic_factors": []
    "questions_to_ask": []
}}

**Example questions to guide your thinking:**
- "What contingency plans are in place if you have a security compromise in your supply chain?"
- "How are you prioritizing technology and security investments versus operational cost control in the next 12 months?"
- "What current cyber resilience strategies do you have in place today and what would you like to improve in the next 6-12 months?"
- "How does the organization manage technical debt and how much technical debt do you have impacting your resilience?"
"""
    return prompt

def parse_groq_response(response: dict) -> dict:
    """
    Parse Groq API response to extract structured JSON output.
    """
    try:
        content = response["choices"][0]["message"]["content"]
        # You could enhance this with json.loads if you force strict JSON output later
        return {"market_analysis": content}
    except (KeyError, IndexError):
        return {"error": "Invalid response from Groq during market analysis."}
