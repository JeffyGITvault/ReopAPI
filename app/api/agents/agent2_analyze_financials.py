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
from app.api.config import DEFAULT_HEADERS, SEARCH_API_KEY, GOOGLE_CSE_ID
import re

logger = logging.getLogger(__name__)

# Groq token limits
GROQ_MAX_TOTAL_TOKENS = 131072
GROQ_MAX_COMPLETION_TOKENS = 32768
GROQ_MAX_PROMPT_TOKENS = GROQ_MAX_TOTAL_TOKENS - GROQ_MAX_COMPLETION_TOKENS
GROQ_SAFE_PROMPT_TOKENS = 90000  # Leave a buffer for org/tier limits

# Use the tokenizer for the primary model
PRIMARY_MODEL = GROQ_MODEL_PRIORITY[0]
try:
    tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-3.3-70b-versatile")
except Exception:
    tokenizer = None
    logger.warning("Could not load tokenizer for meta-llama/Llama-3.3-70b-versatile. Token counting will be approximate.")

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
    Returns a dict with 'item1', 'item2', 'notes', and 'item1_tables' keys.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    text = ' '.join(text.split())
    # Section boundary detection
    item_headers = list(re.finditer(r'(Item\s*\d+[A-Z]?\.?\s*[A-Za-z\s\-&]*)', text, re.IGNORECASE))
    sections = {}
    for idx, match in enumerate(item_headers):
        start = match.start()
        end = item_headers[idx + 1].start() if idx + 1 < len(item_headers) else len(text)
        header = match.group(1).strip()
        sections[header.lower()] = text[start:end].strip()
    # Extract Item 1 and Item 2 using detected boundaries
    item1 = ''
    item2 = ''
    for k in sections:
        if k.startswith('item 1') and not k.startswith('item 1a'):
            item1 = sections[k]
            extraction_notes.append(f"Item 1 extracted using section boundary: '{k}'")
        if k.startswith('item 2') and not k.startswith('item 2a'):
            item2 = sections[k]
            extraction_notes.append(f"Item 2 extracted using section boundary: '{k}'")
    if not item1:
        extraction_notes.append("Item 1 not found using section boundary detection.")
    if not item2:
        extraction_notes.append("Item 2 not found using section boundary detection.")
    # Extract tables from Item 1 (if any)
    item1_tables = []
    if item1:
        # Find the HTML corresponding to Item 1
        # Use regex to find the HTML segment for Item 1
        html_text = html
        item1_html = ''
        item1_match = re.search(r'(Item\s*1\.?[^<]{0,30})(.*?)(Item\s*2\.?|$)', html_text, re.IGNORECASE | re.DOTALL)
        if item1_match:
            item1_html = item1_match.group(2)
        else:
            # fallback: use the whole HTML if not found
            item1_html = html_text
        item1_soup = BeautifulSoup(item1_html, "html.parser")
        tables = item1_soup.find_all('table')
        for table in tables:
            # Convert table to text (or CSV-like string)
            rows = []
            for tr in table.find_all('tr'):
                cells = [td.get_text(separator=" ", strip=True) for td in tr.find_all(['td', 'th'])]
                rows.append(','.join(cells))
            table_text = '\n'.join(rows)
            if table_text.strip():
                item1_tables.append(table_text)
        if item1_tables:
            extraction_notes.append(f"Extracted {len(item1_tables)} tables from Item 1 section.")
        else:
            extraction_notes.append("No tables found in Item 1 section.")
    else:
        extraction_notes.append("No Item 1 section found for table extraction.")
    # Notes extraction: cross-reference Note mentions
    all_notes = re.findall(r'(Note\s*\d+.*?)(?=Note\s*\d+|$)', text, re.IGNORECASE)
    referenced_notes = set(re.findall(r'Note\s*\d+', item1 + item2, re.IGNORECASE))
    notes = [n for n in all_notes if any(ref in n for ref in referenced_notes)]
    if not notes:
        extraction_notes.append("No referenced notes found in Item 1 or 2.")
    notes_text = '\n\n'.join(notes)
    return {"item1": item1, "item2": item2, "notes": notes_text, "item1_tables": item1_tables}

def summarize_section(section: str, max_tokens: int = 10000) -> str:
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
    system_message = (
        "You are a financial analyst. Only output valid JSON. "
        "Do NOT use markdown or code blocks. "
        "Do NOT include control characters. "
        "ALWAYS return valid JSON in the specified format."
    )
    prompt = system_message + f"\nCompare and analyze the following SEC 10-Q filings for {company_name}. For each, only Item 1 (Financial Statements), Item 2 (MD&A), relevant Notes, and extracted tables are included.\n\n"
    for filing in filings:
        label = f"Filing Date: {filing.get('filing_date', 'Unknown')} | Title: {filing.get('title', '')}"
        prompt += f"---\n{label}\nItem 1: Financial Statements\n{filing.get('item1', '')}\n\nItem 2: Management's Discussion and Analysis (MD&A)\n{filing.get('item2', '')}\n\nRelevant Notes\n{filing.get('notes', '')}\n\n"
        # Add all extracted tables from Item 1, all rows, with labels
        tables = filing.get('item1_tables', [])
        if tables:
            prompt += "Extracted Financial Tables from Item 1 (all tables, all rows, pipe-separated):\n"
            for i, table in enumerate(tables):
                rows = table.split('\n')
                header = rows[0] if rows else "(No header)"
                label = f"Table {i+1}: {header}"
                # Priority detection
                if any(x in header.lower() for x in ["balance sheet", "income statement"]):
                    label += " (PRIORITY TABLE)"
                prompt += label + "\n"
                for row in rows:
                    # Convert to pipe-separated (avoid markdown)
                    prompt += ' | '.join([cell.strip() for cell in row.split(',')]) + '\n'
                prompt += '\n'
    prompt += (
        f"Recent News:\n{news}\n\n"
        "Instructions: Analyze the 10-Q filings for key metrics and output revenue, gross margin, and net income in your summary, compare the filings and highlight any trends or changes. "
        "prioritize analysis of Balance Sheet and Income Statement tables from Item 1 and layer in the MD&A and Notes from Item 2. "
        "Summarize key financial trends across the filings, note any risks such as margin declines, revenue declines, and recent events. "
        "show the key metrics in a table format, and show the financial summary in a narrative format. "
        "Only output valid JSON. Respond in the following JSON format:\n"
        "{\n  \"financial_summary\": \"...\",\n  \"key_metrics_table\": \"...\",\n  \"suggested_graph\": \"...\",\n  \"recent_events_summary\": \"...\",\n  \"questions_to_ask\": [\"...\", \"...\"]\n}\n"
    )
    if extraction_notes:
        prompt += f"\n\nExtraction Notes: {'; '.join(extraction_notes)}"
    # FINAL TRUNCATION: Only if prompt exceeds 20,000 tokens
    max_prompt_tokens = 20000
    prompt_token_count = count_tokens(prompt)
    if prompt_token_count > max_prompt_tokens:
        logger.warning(f"Prompt too large ({prompt_token_count} tokens). Truncating to {max_prompt_tokens} tokens.")
        prompt = safe_truncate_prompt(prompt, max_prompt_tokens)
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

def analyze_financials(sec_data: dict, additional_context: dict = None) -> Dict[str, Any]:
    """
    Agent 2: Analyze financials from SEC data, fetch news signals, and with LLM.
    Returns a dict with financial analysis or error.
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
                    if count_tokens(section) > 32000:
                        extraction_notes.append(f"Section '{key}' in filing '{filing.get('filing_date', '')}' was truncated to 32000 tokens.")
                        extracted[key] = safe_truncate_prompt(section, 32000)
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
        # Always use Google Custom Search for news enrichment
        external_signals = fetch_google_company_signals(company_name)
        if not external_signals or 'No public web results found.' in external_signals or 'API key' in external_signals:
            external_signals = generate_synthetic_signals(company_name)
        # --- Add user context to the prompt ---
        ac = additional_context or {}
        user_context_section = (
            "User-provided meeting context (pre-meeting):\n"
            f"- First meeting: {ac.get('first_meeting', 'Not specified')}\n"
            f"- User knowledge: {ac.get('user_knowledge', 'Not specified')}\n"
            f"- Proposed solutions: {ac.get('proposed_solutions', 'Not specified')}\n"
            f"- Wants messaging help: {ac.get('messaging_help', 'Not specified')}\n\n"
        )
        prompt = user_context_section + build_groq_prompt_from_filings(company_name, extracted_filings, external_signals, extraction_notes)
        prompt_token_count = count_tokens(prompt)
        logger.info(f"Prompt token count: {prompt_token_count}")
        if prompt_token_count > GROQ_SAFE_PROMPT_TOKENS:
            extraction_notes.append(f"Prompt was truncated from {prompt_token_count} tokens to {GROQ_SAFE_PROMPT_TOKENS} tokens.")
            prompt = safe_truncate_prompt(prompt, GROQ_SAFE_PROMPT_TOKENS)
        try:
            result = call_groq(
                prompt,
                max_tokens=32768,
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
                        max_tokens=32768,
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
            # Try to extract the largest JSON object using regex
            json_match = re.search(r'\{(?:[^{}]|(?R))*\}', clean_result, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(0))
                except Exception as e2:
                    logger.error(f"Failed to fix Groq output with regex: {e2}")
                    return {"error": f"Groq output was not valid JSON and could not be fixed: {str(e2)}", "notes": extraction_notes}
            else:
                try:
                    fixed = clean_result.replace(",]", "]").replace(",}}", "}}")
                    parsed = json.loads(fixed)
                except Exception as e2:
                    logger.error(f"Failed to fix Groq output: {e2}")
                    return {"error": f"Groq output was not valid JSON and could not be fixed: {str(e2)}", "notes": extraction_notes}
        # Fallback messaging if no real data
        if not parsed or not any(parsed.get(k) for k in ["financial_summary", "key_metrics_table", "recent_events_summary"]):
            return {
                "financial_summary": "No financial data found in filings. Please check the filings manually.",
                "key_metrics_table": {},
                "suggested_graph": "",
                "recent_events_summary": "",
                "questions_to_ask": [],
                "notes": extraction_notes
            }
        # --- Ensure correct types for output fields ---
        key_metrics_table = parsed.get("key_metrics_table", {})
        # Post-process: ensure all values are lists of strings
        def dict_to_list_of_strings(d):
            return [f"{k}: {v}" for k, v in d.items()]
        if isinstance(key_metrics_table, dict):
            for k, v in list(key_metrics_table.items()):
                if isinstance(v, dict):
                    key_metrics_table[k] = dict_to_list_of_strings(v)
                elif isinstance(v, str):
                    key_metrics_table[k] = [v]
                elif isinstance(v, list):
                    # Ensure all elements are strings
                    key_metrics_table[k] = [str(x) for x in v]
                else:
                    key_metrics_table[k] = [str(v)]
        else:
            key_metrics_table = {}
        questions_to_ask = parsed.get("questions_to_ask", [])
        if not isinstance(questions_to_ask, list):
            questions_to_ask = [str(questions_to_ask)] if questions_to_ask else []
        # Remove or blank out suggested_graph
        suggested_graph = ""
        json_payload_for_agents_3_4 = {
            "company_name": company_name,
            "financial_summary": parsed.get("financial_summary", "") if parsed else "",
            "recent_events_summary": parsed.get("recent_events_summary", "") if parsed else "",
            "key_metrics_table": key_metrics_table,
            "suggested_graph": suggested_graph,
            "questions_to_ask": questions_to_ask,
            "notes": extraction_notes
        }
        return json_payload_for_agents_3_4
    except Exception as e:
        logger.error(f"Agent 2 - Financial analysis failed: {e}")
        return {"error": f"Agent 2 - Financial analysis failed: {str(e)}"}

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
        result = call_groq(prompt, max_tokens=32768)
        logger.info("Agent 2 Groq raw output (synthetic signals): %s", result)
        # Always parse and validate as JSON
        clean_result = extract_json_from_llm_output(result) if isinstance(result, str) else result
        try:
            parsed = json.loads(clean_result) if isinstance(clean_result, str) else clean_result
        except Exception as e:
            logger.warning(f"Groq output (synthetic signals) was not valid JSON: {e}. Attempting to fix.")
            try:
                fixed = clean_result.replace(",]", "]").replace(",}}", "}}")
                parsed = json.loads(fixed)
            except Exception as e2:
                logger.error(f"Failed to fix Groq output (synthetic signals): {e2}")
                return json.dumps({
                    "financial_summary": "No synthetic signals available.",
                    "key_metrics_table": "",
                    "suggested_graph": "",
                    "recent_events_summary": "",
                    "questions_to_ask": []
                })
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
