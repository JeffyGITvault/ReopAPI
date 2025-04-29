# app/api/agents/agent2_analyze_financials.py

import requests
import os
from app.api.groq_client import call_groq


def analyze_financials(sec_data: dict) -> dict:
    """
    Agent 2: Analyze company's latest financials based on the most recent 10-Q and contextual signals.
    """
    try:
        filings = sec_data.get("filings", [])
        if not filings:
            return {"error": "No 10-Q filings found for financial analysis."}

        latest_filing = filings[0]
        html_url = latest_filing.get("html_url", "")

        if not html_url or html_url == "Unavailable":
            return {"error": "No valid 10-Q URL available for financial analysis."}

        # Fetch 10-Q HTML
        headers = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
        response = requests.get(html_url, headers=headers, timeout=10)
        response.raise_for_status()
        ten_q_html = response.text

        # Fetch real news if Bing key exists, otherwise simulate via Groq
        company_name = sec_data.get("company_name", "the company")
        if os.getenv("BING_API_KEY"):
            external_signals = fetch_recent_signals(company_name)
        else:
            external_signals = generate_synthetic_signals(company_name)

        # Build Groq prompt
        prompt = build_financial_prompt(ten_q_html, external_signals)

        # Call Groq LLM
        result = call_groq(prompt)

        return parse_groq_response(result)

    except Exception as e:
        return {"error": f"Agent 2 - Financial analysis failed: {str(e)}"}


def fetch_recent_signals(company_name: str) -> str:
    """
    Pull recent financial or strategic developments from news and professional sources using Bing.
    """
    try:
        headers = {"Ocp-Apim-Subscription-Key": os.getenv("BING_API_KEY")}
        query = f"""
            "{company_name}" (earnings OR revenue OR margin OR debt OR funding OR hiring OR layoff OR transformation)
            site:reuters.com OR site:bloomberg.com OR site:wsj.com OR site:linkedin.com OR site:forbes.com OR site:techcrunch.com OR site:seekingalpha.com OR site:finance.yahoo.com OR site:x.com
        """.replace("\n", " ")

        params = {
            "q": query,
            "count": 4
        }

        response = requests.get("https://api.bing.microsoft.com/v7.0/news/search", headers=headers, params=params)
        response.raise_for_status()

        articles = response.json().get("value", [])
        if not articles:
            return "No significant recent headlines found."

        summary = "\n".join([f"- {a['name']} ({a['url']})" for a in articles])
        return summary

    except Exception as e:
        return f"Failed to fetch real signals: {str(e)}\n" + generate_synthetic_signals(company_name)


def generate_synthetic_signals(company_name: str) -> str:
    """
    Uses Groq to simulate recent external signals when real news is unavailable.
    """
    prompt = f"""
You are simulating a market analyst reviewing financial news, social signals, and analyst coverage of "{company_name}".

List 2–3 notable financial or strategic developments from the last 90 days that may affect how consultants or sellers engage with the company.

Be plausible and realistic — earnings beats, layoffs, customer wins, executive changes, downgrades, supply chain issues, or product delays.

Respond with a short bullet list.
"""
    try:
        result = call_groq(prompt)
        content = result["choices"][0]["message"]["content"]
        return content.strip()
    except Exception as e:
        return f"(Fallback failed: {str(e)})"


def build_financial_prompt(html_content: str, external_signals: str) -> str:
    """
    Build a structured Groq prompt to analyze company financials and signal context.
    """
    prompt = f"""
You are a junior financial analyst building a fast-read briefing for consultants and sales leads.

Given:
- A company's most recent 10-Q HTML (SEC filing)
- External signals from news, industry sources, and professional platforms

Summarize:
- Revenue trend (YoY or QoQ)
- Gross margin trend (up/down/flat)
- Cash position and debt level (from balance sheet)
- Liquidity and operational flexibility
- Any flagged risks (e.g., high leverage, negative cash flow)
- One table of key financials
- One graph suggestion (e.g., revenue vs margin, debt vs cash)
- 2–3 smart financial questions to ask in client meetings

Also include:
- A short summary of external sentiment or developments that may be relevant to the company’s current strategy or outlook

SEC 10-Q (truncated):

{html_content[:4000]}

External Signals:

{external_signals}

Respond in the following JSON format:

{{
  "financial_summary": "...",
  "key_metrics_table": "...",
  "suggested_graph": "...",
  "recent_events_summary": "...",
  "questions_to_ask": ["...", "..."]
}}
"""
    return prompt


def parse_groq_response(response: dict) -> dict:
    """
    Parse structured Groq response.
    """
    try:
        content = response["choices"][0]["message"]["content"]
        return {"analysis": content}
    except (KeyError, IndexError):
        return {"error": "Invalid response from Groq during financial analysis."}
