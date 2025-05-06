# app/api/agents/agent2_analyze_financials.py

import logging
import requests
import os
import json
from typing import Dict, Any, Optional
from urllib.parse import quote_plus
from transformers import AutoTokenizer
from app.api.groq_client import call_groq, GROQ_MODEL_PRIORITY
from app.api.config import NEWSDATA_API_KEY, DEFAULT_HEADERS, SEARCH_API_KEY, GOOGLE_CSE_ID

logger = logging.getLogger(__name__)

# Groq token limits
GROQ_MAX_TOTAL_TOKENS = 131072
GROQ_MAX_COMPLETION_TOKENS = 8192
GROQ_MAX_PROMPT_TOKENS = GROQ_MAX_TOTAL_TOKENS - GROQ_MAX_COMPLETION_TOKENS
GROQ_SAFE_PROMPT_TOKENS = 90000  # Leave a buffer for org/tier limits

# Use the tokenizer for the primary model
PRIMARY_MODEL = GROQ_MODEL_PRIORITY[0]
try:
    tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-3-70b")
except Exception:
    tokenizer = None
    logger.warning("Could not load tokenizer for meta-llama/Llama-3-70b. Token counting will be approximate.")

def count_tokens(text: str) -> int:
    if tokenizer:
        return len(tokenizer.encode(text))
    # Fallback: rough estimate
    return int(len(text.split()) / 0.75)

def safe_truncate_prompt(prompt: str, max_tokens: int) -> str:
    if tokenizer:
        tokens = tokenizer.encode(prompt)
        if len(tokens) > max_tokens:
            logger.warning(f"Prompt too large ({len(tokens)} tokens). Truncating to {max_tokens} tokens.")
            tokens = tokens[:max_tokens]
            return tokenizer.decode(tokens)
        return prompt
    # Fallback: rough truncation
    words = prompt.split()
    allowed_words = int(max_tokens * 0.75)
    if len(words) > allowed_words:
        logger.warning(f"Prompt too large (approx {len(words)/0.75} tokens). Truncating to {allowed_words} words.")
        return ' '.join(words[:allowed_words])
    return prompt

def fetch_google_company_signals(company_name: str) -> str:
    """
    Fetch recent company news using Google Custom Search as a fallback enrichment source.
    """
    if not SEARCH_API_KEY or not GOOGLE_CSE_ID:
        logger.warning("Google Search API key or CSE ID not set. Skipping Google fetch.")
        return "Google Search API key or CSE ID not set."
    try:
        query = f'"{company_name}" site:businesswire.com OR site:bloomberg.com OR site:reuters.com OR site:wsj.com'
        params = {
            "key": SEARCH_API_KEY,
            "cx": GOOGLE_CSE_ID,
            "q": query,
            "num": 5
        }
        response = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=10)
        response.raise_for_status()
        items = response.json().get("items", [])
        if not items:
            return "No public web results found."
        return "\n".join([
            f"- [{item['title']}]({item['link']}) — {item.get('snippet', 'No snippet')}"
            for item in items
        ])
    except Exception as e:
        logger.warning(f"Google Search API fetch failed for {company_name}: {e}")
        return f"Google Search API fetch failed: {str(e)}"

def analyze_financials(sec_data: dict) -> Dict[str, Any]:
    """
    Agent 2: Analyze financials from SEC data, fetch news signals, and summarize with LLM.
    Returns a dict with financial summary or error.
    """
    note = None
    try:
        source_type = sec_data.get("source", "")
        company_name = sec_data.get("company_name", "the company")

        if source_type == "html":
            ten_q_html = "\n\n".join(sec_data.get("chunks", []))
            logger.info("Agent 2 received pre-parsed 10-Q chunks.")
        elif source_type == "url":
            html_url = sec_data.get("url", "")
            if not html_url:
                return {"error": "No valid 10-Q URL provided for analysis."}
            response = requests.get(html_url, headers=DEFAULT_HEADERS, timeout=10)
            response.raise_for_status()
            ten_q_html = response.text
            logger.info("Agent 2 fetched 10-Q HTML from URL.")
        else:
            filings = sec_data.get("filings", [])
            if not filings:
                return {"error": "No 10-Q filings found for financial analysis."}
            latest_filing = filings[0]
            html_url = latest_filing.get("html_url", "")
            if not html_url or html_url == "Unavailable":
                return {"error": "No valid 10-Q URL available for financial analysis."}
            response = requests.get(html_url, headers=DEFAULT_HEADERS, timeout=10)
            response.raise_for_status()
            ten_q_html = response.text
            logger.info("Agent 2 fetched fallback 10-Q HTML from filings.")

        # Truncate 10-Q HTML if too large for Groq
        token_count = count_tokens(ten_q_html)
        if token_count > GROQ_MAX_PROMPT_TOKENS:
            note = f"10-Q HTML was truncated from {token_count} tokens to {GROQ_SAFE_PROMPT_TOKENS} tokens to fit model limits."
            ten_q_html = safe_truncate_prompt(ten_q_html, GROQ_SAFE_PROMPT_TOKENS)

        external_signals = (
            fetch_recent_signals(company_name)
            if NEWSDATA_API_KEY else fetch_google_company_signals(company_name)
        )
        if not external_signals or 'No public web results found.' in external_signals or 'API key' in external_signals:
            external_signals = generate_synthetic_signals(company_name)

        prompt = build_financial_prompt(ten_q_html, external_signals)
        prompt_token_count = count_tokens(prompt)
        if prompt_token_count > GROQ_SAFE_PROMPT_TOKENS:
            note = (note or "") + f" Prompt was truncated from {prompt_token_count} tokens to {GROQ_SAFE_PROMPT_TOKENS} tokens."
            prompt = safe_truncate_prompt(prompt, GROQ_SAFE_PROMPT_TOKENS)

        # Try Groq call, retry with truncated prompt if context error
        try:
            result = call_groq(prompt, max_tokens=GROQ_MAX_COMPLETION_TOKENS, include_domains=["sec.gov"])
        except Exception as e:
            if "context_length_exceeded" in str(e) or "Request too large" in str(e):
                note = (note or "") + " Groq context limit exceeded, prompt was truncated and retried."
                prompt = safe_truncate_prompt(prompt, GROQ_SAFE_PROMPT_TOKENS // 2)
                try:
                    result = call_groq(prompt, max_tokens=GROQ_MAX_COMPLETION_TOKENS, include_domains=["sec.gov"])
                except Exception as e2:
                    logger.error(f"Agent 2 - Financial analysis failed after retry: {e2}")
                    return {"error": f"Agent 2 - Financial analysis failed after retry: {str(e2)}", "note": note}
            else:
                logger.error(f"Agent 2 - Financial analysis failed: {e}")
                return {"error": f"Agent 2 - Financial analysis failed: {str(e)}", "note": note}

        logger.info("Agent 2 Groq raw output: %s", result)
        parsed = parse_groq_response(result)

        # JSON handoff block to Agent 3 and Agent 4
        json_payload_for_agents_3_4 = {
            "company_name": company_name,
            "financial_summary": parsed.get("financial_summary", ""),
            "recent_events_summary": parsed.get("recent_events_summary", ""),
            "key_metrics_table": parsed.get("key_metrics_table", ""),
        }
        if note:
            json_payload_for_agents_3_4["note"] = note.strip()
        return json_payload_for_agents_3_4
    except Exception as e:
        logger.error(f"Agent 2 - Financial analysis failed: {e}")
        return {"error": f"Agent 2 - Financial analysis failed: {str(e)}", "note": note}


def fetch_recent_signals(company_name: str) -> str:
    """
    Fetch recent news signals for a company using NewsData.io. Sanitize and URL-encode queries. Handle 422 errors. Fallback to Google CSE or synthetic signals.
    """
    try:
        headers = {"Content-Type": "application/json"}
        # Sanitize and URL-encode the query
        query = quote_plus(company_name)
        params = {
            "apikey": NEWSDATA_API_KEY,
            "q": query,
            "language": "en",
            "category": "business",
            "country": "us",
            "page": 1
        }
        response = requests.get("https://newsdata.io/api/1/news", params=params, headers=headers, timeout=10)
        if response.status_code == 422:
            logger.warning(f"NewsData.io 422 error for query: {company_name}. Falling back to Google CSE.")
            google_signals = fetch_google_company_signals(company_name)
            if 'No public web results found.' not in google_signals and 'API key' not in google_signals:
                return google_signals
            return generate_synthetic_signals(company_name)
        response.raise_for_status()
        articles = response.json().get("results", [])
        if not articles:
            logger.warning(f"No NewsData.io articles for {company_name}. Falling back to Google CSE.")
            google_signals = fetch_google_company_signals(company_name)
            if 'No public web results found.' not in google_signals and 'API key' not in google_signals:
                return google_signals
            return generate_synthetic_signals(company_name)
        summary = "\n".join([f"- {a['title']} ({a['link']})" for a in articles[:5]])
        return summary
    except Exception as e:
        logger.warning(f"Failed to fetch real signals: {e}. Falling back to Google CSE.")
        google_signals = fetch_google_company_signals(company_name)
        if 'No public web results found.' not in google_signals and 'API key' not in google_signals:
            return google_signals
        return f"Failed to fetch real signals: {str(e)}\n" + generate_synthetic_signals(company_name)


def generate_synthetic_signals(company_name: str) -> str:
    """
    Generate plausible synthetic financial signals for a company.
    """
    prompt = f"""
You are simulating a market analyst reviewing financial news, social signals, and analyst coverage of \"{company_name}\".

List 2–3 notable financial or strategic developments from the last 90 days that may affect how consultants or sellers engage with the company.

Be plausible and realistic — earnings beats, layoffs, customer wins, executive changes, downgrades, supply chain issues, or product delays.

Respond in the following JSON format:
{{
  "financial_summary": "...",
  "key_metrics_table": "...",
  "suggested_graph": "...",
  "recent_events_summary": "...",
  "questions_to_ask": ["...", "..."]
}}
"""
    try:
        result = call_groq(prompt, max_tokens=GROQ_MAX_COMPLETION_TOKENS)
        logger.info("Agent 2 Groq raw output (synthetic signals): %s", result)
        parsed = parse_groq_response(result)
        return parsed.get("financial_summary", "") if isinstance(parsed, dict) else str(parsed)
    except Exception as e:
        logger.error(f"Failed to generate synthetic signals: {e}")
        return "No synthetic signals available."


def build_financial_prompt(html_content: str, external_signals: str) -> str:
    """
    Build a financial analysis prompt for the LLM.
    """
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
- A short summary of external sentiment or developments that may be relevant to the company's current strategy or outlook

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


def parse_groq_response(response: Any) -> Dict[str, Any]:
    """
    Parse the response from Groq, handling both string and dict input. Fallback if not valid JSON.
    """
    try:
        return json.loads(response) if isinstance(response, str) else response
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON returned from Groq: {e}. Raw output: {response}")
        return {"error": f"Invalid JSON returned from Groq: {str(e)}", "raw_output": response}
