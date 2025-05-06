# app/api/agents/agent2_analyze_financials.py

import logging
import requests
import os
import json
from typing import Dict, Any, Optional, List
from urllib.parse import quote_plus
from transformers import AutoTokenizer
from bs4 import BeautifulSoup
from app.api.groq_client import call_groq, GROQ_MODEL_PRIORITY
from app.api.config import NEWSDATA_API_KEY, DEFAULT_HEADERS, SEARCH_API_KEY, GOOGLE_CSE_ID
import re

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

def extract_10q_sections(html: str, extraction_notes: List[str]) -> Dict[str, str]:
    """
    Extract Item 1 (Financial Statements), Item 2 (MD&A), and relevant Notes from 10-Q HTML/text.
    Returns a dict with 'item1', 'item2', and 'notes' keys.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    text = ' '.join(text.split())
    # Robust regex for Item 1
    item1_patterns = [
        r'(Item\s*1\.?\s*Financial Statements.*?)(Item\s*2\.?\s*Management)',
        r'(Item\s*1\.?\s*Financial Information.*?)(Item\s*2\.?\s*Management)',
        r'(Item\s*1\.?\s*Condensed Consolidated Financial Statements.*?)(Item\s*2\.?\s*Management)'
    ]
    item1 = ""
    for pat in item1_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            item1 = m.group(1)
            break
    if not item1:
        extraction_notes.append("Item 1 not found with standard patterns.")
    # Robust regex for Item 2
    item2_patterns = [
        r'(Item\s*2\.?\s*Management.*?)(Item\s*3\.?|Item\s*4\.?|PART\s*II)',
        r'(Item\s*2\.?\s*Management.*?)(PART\s*II)'
    ]
    item2 = ""
    for pat in item2_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            item2 = m.group(1)
            break
    if not item2:
        extraction_notes.append("Item 2 not found with standard patterns.")
    # Notes extraction: cross-reference Note mentions
    notes_section = ""
    all_notes = re.findall(r'(Note\s*\d+.*?)(?=Note\s*\d+|$)', text, re.IGNORECASE)
    referenced_notes = set(re.findall(r'Note\s*\d+', item1 + item2, re.IGNORECASE))
    notes = [n for n in all_notes if any(ref in n for ref in referenced_notes)]
    if not notes:
        extraction_notes.append("No referenced notes found in Item 1 or 2.")
    notes_text = '\n\n'.join(notes)
    return {"item1": item1, "item2": item2, "notes": notes_text}

def summarize_section(section: str, max_tokens: int = 3000) -> str:
    """
    Simple extractive summary: return the first N tokens of the section.
    """
    if not section:
        return ""
    if count_tokens(section) <= max_tokens:
        return section
    # Truncate to max_tokens
    return safe_truncate_prompt(section, max_tokens)

def build_groq_prompt_from_filings(company_name: str, filings: List[Dict[str, str]], news: str = "", extraction_notes: List[str] = None) -> str:
    system_message = "You are a financial analyst. Only output valid JSON."
    prompt = system_message + f"\nCompare and analyze the following SEC 10-Q filings for {company_name}. For each, only Item 1 (Financial Statements), Item 2 (MD&A), and relevant Notes are included.\n\n"
    for filing in filings:
        label = f"Filing Date: {filing.get('filing_date', 'Unknown')} | Title: {filing.get('title', '')}"
        prompt += f"---\n{label}\nItem 1: Financial Statements\n{filing.get('item1', '')}\n\nItem 2: Management's Discussion and Analysis (MD&A)\n{filing.get('item2', '')}\n\nRelevant Notes\n{filing.get('notes', '')}\n\n"
    prompt += f"Recent News:\n{news}\n\nSummarize key financial trends across the filings, note any risks such as margin declines, revenue declines, and recent events. Focus on management's discussion, financial condition, and any important notes. Compare the filings and highlight any trends or changes. Only output valid JSON. Respond in the following JSON format:\n{{\n  \"financial_summary\": \"...\",\n  \"key_metrics_table\": \"...\",\n  \"suggested_graph\": \"...\",\n  \"recent_events_summary\": \"...\",\n  \"questions_to_ask\": [\"...\", \"...\"]\n}}\n"
    if extraction_notes:
        prompt += f"\n\nExtraction Notes: {'; '.join(extraction_notes)}"
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

def extract_json_from_llm_output(output: str) -> str:
    # Remove markdown code block markers if present
    if output.strip().startswith("```"):
        # Remove the first line (``` or ```json) and the last line (```)
        lines = output.strip().splitlines()
        # Remove first and last line if they are code block markers
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        output = "\n".join(lines)
    # Optionally, remove any leading/trailing whitespace
    return output.strip()

def analyze_financials(sec_data: dict) -> Dict[str, Any]:
    """
    Agent 2: Analyze financials from SEC data, fetch news signals, and summarize with LLM.
    Returns a dict with financial summary or error.
    """
    note = None
    try:
        company_name = sec_data.get("company_name", "the company")
        filings = sec_data.get("filings", [])
        if not filings:
            return {"error": "No 10-Q filings found for financial analysis."}
        extracted_filings = []
        missing_filings = 0
        extraction_notes = []
        for filing in filings:
            url = filing.get("html_url")
            if not url or url == "Unavailable":
                missing_filings += 1
                continue
            try:
                response = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
                response.raise_for_status()
                html = response.text
                extracted = extract_10q_sections(html, extraction_notes)
                # Truncate each section individually before summarizing
                for key in ["item1", "item2", "notes"]:
                    section = extracted.get(key, "")
                    if count_tokens(section) > 3000:
                        extraction_notes.append(f"Section '{key}' in filing '{filing.get('filing_date', '')}' was truncated to 3000 tokens.")
                        extracted[key] = safe_truncate_prompt(section, 3000)
                extracted["filing_date"] = filing.get("filing_date", "")
                extracted["title"] = filing.get("title", company_name)
                extracted_filings.append(extracted)
            except Exception as e:
                logger.warning(f"Failed to fetch or extract filing at {url}: {e}")
                extraction_notes.append(f"Failed to fetch or extract filing at {url}: {e}")
                missing_filings += 1
        if not extracted_filings:
            return {"error": "No valid 10-Q filings could be processed."}
        if missing_filings:
            extraction_notes.append(f"{missing_filings} filings could not be processed and were skipped.")
        external_signals = (
            fetch_recent_signals(company_name)
            if NEWSDATA_API_KEY else fetch_google_company_signals(company_name)
        )
        if not external_signals or 'No public web results found.' in external_signals or 'API key' in external_signals:
            external_signals = generate_synthetic_signals(company_name)
        prompt = build_groq_prompt_from_filings(company_name, extracted_filings, external_signals, extraction_notes)
        prompt_token_count = count_tokens(prompt)
        logger.info(f"Prompt token count: {prompt_token_count}")
        if prompt_token_count > GROQ_SAFE_PROMPT_TOKENS:
            extraction_notes.append(f"Prompt was truncated from {prompt_token_count} tokens to {GROQ_SAFE_PROMPT_TOKENS} tokens.")
            prompt = safe_truncate_prompt(prompt, GROQ_SAFE_PROMPT_TOKENS)
        try:
            result = call_groq(
                prompt,
                max_tokens=GROQ_MAX_COMPLETION_TOKENS,
                include_domains=["sec.gov"],
                response_format={"type": "json_object"}
            )
        except Exception as e:
            if "context_length_exceeded" in str(e) or "Request too large" in str(e):
                extraction_notes.append("Groq context limit exceeded, prompt was truncated and retried.")
                prompt = safe_truncate_prompt(prompt, GROQ_SAFE_PROMPT_TOKENS // 2)
                try:
                    result = call_groq(
                        prompt,
                        max_tokens=GROQ_MAX_COMPLETION_TOKENS,
                        include_domains=["sec.gov"],
                        response_format={"type": "json_object"}
                    )
                except Exception as e2:
                    logger.error(f"Agent 2 - Financial analysis failed after retry: {e2}")
                    return {"error": f"Agent 2 - Financial analysis failed after retry: {str(e2)}", "notes": extraction_notes}
            else:
                logger.error(f"Agent 2 - Financial analysis failed: {e}")
                return {"error": f"Agent 2 - Financial analysis failed: {str(e)}", "notes": extraction_notes}
        logger.info("Agent 2 Groq raw output: %s", result)
        clean_result = extract_json_from_llm_output(result) if isinstance(result, str) else result
        try:
            parsed = json.loads(clean_result) if isinstance(clean_result, str) else clean_result
        except Exception as e:
            logger.warning(f"Groq output was not valid JSON: {e}. Attempting to fix.")
            try:
                fixed = clean_result.replace(",]", "]").replace(",}}", "}}")
                parsed = json.loads(fixed)
            except Exception as e2:
                logger.error(f"Failed to fix Groq output: {e2}")
                return {"error": f"Groq output was not valid JSON and could not be fixed: {str(e2)}", "notes": extraction_notes}
        json_payload_for_agents_3_4 = {
            "company_name": company_name,
            "financial_summary": parsed.get("financial_summary", "") if parsed else "",
            "recent_events_summary": parsed.get("recent_events_summary", "") if parsed else "",
            "key_metrics_table": parsed.get("key_metrics_table", "") if parsed else "",
            "notes": extraction_notes
        }
        return json_payload_for_agents_3_4
    except Exception as e:
        logger.error(f"Agent 2 - Financial analysis failed: {e}")
        return {"error": f"Agent 2 - Financial analysis failed: {str(e)}"}


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
        # Return the full JSON structure for consistency
        if isinstance(parsed, dict):
            return json.dumps(parsed)
        return str(parsed)
    except Exception as e:
        logger.error(f"Failed to generate synthetic signals: {e}")
        return json.dumps({
            "financial_summary": "No synthetic signals available.",
            "key_metrics_table": "",
            "suggested_graph": "",
            "recent_events_summary": "",
            "questions_to_ask": []
        })


def parse_groq_response(response: Any) -> Dict[str, Any]:
    """
    Parse the response from Groq, handling both string and dict input. Fallback if not valid JSON.
    """
    try:
        if isinstance(response, str):
            response = extract_json_from_llm_output(response)
        return json.loads(response) if isinstance(response, str) else response
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON returned from Groq: {e}. Raw output: {response}")
        return {"error": f"Invalid JSON returned from Groq: {str(e)}", "raw_output": response}
