# app/api/agents/agent2_analyze_financials.py

import requests
from app.api.groq_client import call_groq

def analyze_financials(sec_data: dict) -> dict:
    """
    Agent 2: Analyze company's latest financials based on the most recent 10-Q.
    """
    try:
        filings = sec_data.get("filings", [])

        if not filings:
            return {"error": "No 10-Q filings found for financial analysis."}

        latest_filing = filings[0]  # Always prioritize the most recent
        html_url = latest_filing.get("html_url", "")

        if not html_url or html_url == "Unavailable":
            return {"error": "No valid 10-Q URL available for financial analysis."}

        # Fetch the 10-Q HTML Content
        headers = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
        try:
            response = requests.get(html_url, headers=headers, timeout=10)
            response.raise_for_status()
            ten_q_html = response.text
        except Exception as e:
            return {"error": f"Failed to fetch 10-Q HTML: {str(e)}"}

        # Prepare Groq Prompt
        prompt = build_financial_prompt(ten_q_html)

        # Call Groq LLM
        result = call_groq(prompt)

        # Parse Groq Output
        parsed_analysis = parse_groq_response(result)

        return parsed_analysis

    except Exception as e:
        return {"error": f"Agent 2 - Financial analysis failed: {str(e)}"}

def build_financial_prompt(html_content: str) -> str:
    """
    Build a prompt for Groq to analyze the financials from the 10-Q.
    """
    prompt = f"""
You are a financial analyst reviewing a company's 10-Q SEC filing.

Given the following HTML document (truncated for brevity), extract and summarize:
- Revenue growth or decline trends
- EBITDA or operating margins
- Cash flow health
- Debt levels and debt-to-equity ratios
- Any risks or concerns mentioned

Then suggest:
- One table showing key metrics
- One graph that could visualize revenue or margin trends

HTML snippet (start):

{html_content[:4000]}   <-- [Truncate at 4000 chars to avoid token overload]

[...truncated for brevity]

Summarize clearly in JSON format.
"""
    return prompt

def parse_groq_response(response: dict) -> dict:
    """
    Parse Groq API response to extract JSON output.
    """
    try:
        content = response["choices"][0]["message"]["content"]
        # You could enhance with better JSON parsing if Groq returns strict JSON
        return {"analysis": content}
    except (KeyError, IndexError):
        return {"error": "Invalid response from Groq during financial analysis."}
