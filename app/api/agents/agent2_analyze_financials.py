# app/api/agents/agent2_analyze_financials.py

import requests
import os
import json
from app.api.groq_client import call_groq

def analyze_financials(sec_data: dict) -> dict:
    try:
        source_type = sec_data.get("source", "")
        company_name = sec_data.get("company_name", "the company")

        if source_type == "html":
            ten_q_html = "\n\n".join(sec_data.get("chunks", []))
            print("Agent 2 received pre-parsed 10-Q chunks.")

        elif source_type == "url":
            html_url = sec_data.get("url", "")
            if not html_url:
                return {"error": "No valid 10-Q URL provided for analysis."}
            headers = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
            response = requests.get(html_url, headers=headers, timeout=10)
            response.raise_for_status()
            ten_q_html = response.text
            print("Agent 2 fetched 10-Q HTML from URL.")

        else:
            filings = sec_data.get("filings", [])
            if not filings:
                return {"error": "No 10-Q filings found for financial analysis."}

            latest_filing = filings[0]
            html_url = latest_filing.get("html_url", "")
            if not html_url or html_url == "Unavailable":
                return {"error": "No valid 10-Q URL available for financial analysis."}

            headers = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
            response = requests.get(html_url, headers=headers, timeout=10)
            response.raise_for_status()
            ten_q_html = response.text
            print("Agent 2 fetched fallback 10-Q HTML from filings.")

        if os.getenv("NEWSDATA_API_KEY"):
            external_signals = fetch_recent_signals(company_name)
        else:
            external_signals = generate_synthetic_signals(company_name)

        prompt = build_financial_prompt(ten_q_html, external_signals)
        result = call_groq(prompt)
        print("Agent 2 Groq raw output:", result)
        parsed = parse_groq_response(result)

        # JSON handoff block to Agent 3 and Agent 4
        json_payload_for_agents_3_4 = {
            "company_name": company_name,
            "financial_summary": parsed.get("financial_summary", ""),
            "recent_events_summary": parsed.get("recent_events_summary", ""),
            "key_metrics_table": parsed.get("key_metrics_table", ""),
        }

        return json_payload_for_agents_3_4

    except Exception as e:
        return {"error": f"Agent 2 - Financial analysis failed: {str(e)}"}

def fetch_recent_signals(company_name: str) -> str:
    try:
        headers = {"Content-Type": "application/json"}
        params = {
            "apikey": os.getenv("NEWSDATA_API_KEY"),
            "q": company_name,
            "language": "en",
            "category": "business",
            "country": "us",
            "page": 1
        }
        response = requests.get("https://newsdata.io/api/1/news", params=params, headers=headers, timeout=10)
        response.raise_for_status()
        articles = response.json().get("results", [])

        if not articles:
            return "No recent news found."

        summary = "\n".join([f"- {a['title']} ({a['link']})" for a in articles[:5]])
        return summary

    except Exception as e:
        return f"Failed to fetch real signals: {str(e)}\n" + generate_synthetic_signals(company_name)

def generate_synthetic_signals(company_name: str) -> str:
    prompt = f"""
You are simulating a market analyst reviewing financial news, social signals, and analyst coverage of \"{company_name}\".

List 2–3 notable financial or strategic developments from the last 90 days that may affect how consultants or sellers engage with the company.

Be plausible and realistic — earnings beats, layoffs, customer wins, executive changes, downgrades, supply chain issues, or product delays.

Respond with a short bullet list.
"""
   try:
       result = call_groq(prompt)  # returns a JSON *string*
       print("Agent 2 Groq raw output:", result)
       parsed = parse_groq_response(result)  # parses the JSON string into a dict



def build_financial_prompt(html_content: str, external_signals: str) -> str:
    prompt = f"""
You are a junior financial analyst building a fast-read briefing for consultants and sales leads.

Given:
- A company's most recent 10-Q HTML (SEC filing)
- If the company has no 10-Q HTML data, use general indsutry analysis based on public companies and possible competitors to our reference comapny
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

SEC 10-Q:

{html_content}

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
    try:
        return json.loads(response) if isinstance(response, str) else response
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON returned from Groq: {str(e)}"}
