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
import pandas as pd

logger = logging.getLogger(__name__)

# Groq token limits
GROQ_MAX_TOTAL_TOKENS = 131072
GROQ_MAX_COMPLETION_TOKENS = 32768
GROQ_MAX_PROMPT_TOKENS = GROQ_MAX_TOTAL_TOKENS - GROQ_MAX_COMPLETION_TOKENS
GROQ_SAFE_PROMPT_TOKENS = 90000  # Leave a buffer for org/tier limits
GROQ_SOFT_EXTRACTION_TOKEN_LIMIT = 100000  # Soft limit for extraction payload

# Use the tokenizer for the primary model
PRIMARY_MODEL = GROQ_MODEL_PRIORITY[0]
try:
    tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-3.3-70b-versatile")
except Exception:
    tokenizer = None
    logger.warning("Could not load tokenizer for meta-llama/Llama-3.3-70b-versatile. Token counting will be approximate.")

def count_tokens(text: str) -> int:
    """
    Count the number of tokens in a text string using the tokenizer, or estimate if unavailable.
    """
    if tokenizer:
        return len(tokenizer.encode(text))
    # Fallback: rough estimate
    return int(len(text.split()) / 0.75)

def safe_truncate_prompt(prompt: str, max_tokens: int) -> str:
    """
    Truncate a prompt to a maximum number of tokens, using the tokenizer if available.
    """
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
    # Modularized: Extract tables from Item 1 (if any)
    item1_tables = _extract_tables_from_item1(html, item1, extraction_notes)
    # Modularized: Extract notes
    notes_text = _extract_referenced_notes(text, item1, item2, extraction_notes)
    return {"item1": item1, "item2": item2, "notes": notes_text, "item1_tables": item1_tables}

def _extract_tables_from_item1(html: str, item1: str, extraction_notes: list) -> list:
    """
    Extract tables from the Item 1 section of the 10-Q HTML.
    Returns a list of table strings.
    """
    try:
        if not item1:
            extraction_notes.append("No Item 1 section found for table extraction.")
            return []
        html_text = html
        item1_html = ''
        item1_match = re.search(r'(Item\s*1\.?[^<]{0,30})(.*?)(Item\s*2\.?|$)', html_text, re.IGNORECASE | re.DOTALL)
        if item1_match:
            item1_html = item1_match.group(2)
        else:
            item1_html = html_text
        item1_soup = BeautifulSoup(item1_html, "html.parser")
        tables = item1_soup.find_all('table')
        item1_tables = []
        for table in tables:
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
        return item1_tables
    except Exception as e:
        extraction_notes.append(f"Error extracting tables from Item 1: {e}")
        logger.warning(f"Error extracting tables from Item 1: {e}", exc_info=True)
        return []

def _extract_referenced_notes(text: str, item1: str, item2: str, extraction_notes: list) -> str:
    """
    Extract referenced notes from the 10-Q text, cross-referencing mentions in Item 1 and 2.
    Returns a string of concatenated notes.
    """
    try:
        all_notes = re.findall(r'(Note\s*\d+.*?)(?=Note\s*\d+|$)', text, re.IGNORECASE)
        referenced_notes = set(re.findall(r'Note\s*\d+', item1 + item2, re.IGNORECASE))
        notes = [n for n in all_notes if any(ref in n for ref in referenced_notes)]
        if not notes:
            extraction_notes.append("No referenced notes found in Item 1 or 2.")
        return '\n\n'.join(notes)
    except Exception as e:
        extraction_notes.append(f"Error extracting referenced notes: {e}")
        logger.warning(f"Error extracting referenced notes: {e}", exc_info=True)
        return ""

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

REQUIRED_METRICS = [
    "Revenue",
    "Gross Margin",
    "Net Income",
    "Cost of Goods Sold",
    
    "Debt to Equity Ratio",
    "Liquidity Ratio"
]

def normalize_key_metrics_table(table: dict) -> dict:
    """
    Ensure the key_metrics_table is a dict of {quarter: {metric: value, ...}},
    with all REQUIRED_METRICS present for each quarter. Fill missing with blank or 'Not Provided'.
    Accepts either dict or list of dicts from LLM.
    """
    if not table:
        return {}
    # If already in correct format
    if isinstance(table, dict):
        quarters = list(table.keys())
        out = {}
        for q in quarters:
            metrics = table[q] if isinstance(table[q], dict) else {}
            out[q] = {m: metrics.get(m, "Not Provided") for m in REQUIRED_METRICS}
        return out
    # If list of dicts (e.g., [{"quarter":..., "Revenue":...}, ...])
    if isinstance(table, list):
        out = {}
        for entry in table:
            q = entry.get("quarter") or entry.get("Quarter")
            if not q:
                continue
            out[q] = {m: entry.get(m, "Not Provided") for m in REQUIRED_METRICS}
        return out
    # If string or unknown, return empty
    return {}

def build_groq_prompt_from_filings(company_name: str, filings: List[Dict[str, str]], news: str = "", extraction_notes: List[str] = None) -> str:
    """
    Build a prompt for the LLM to analyze SEC 10-Q filings, including extracted sections and news.
    Returns the prompt string.
    """
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
        tables = filing.get('item1_tables', [])
        if tables:
            prompt += "Extracted Financial Tables from Item 1 (all tables, all rows, pipe-separated):\n"
            for i, table in enumerate(tables):
                rows = table.split('\n')
                header = rows[0] if rows else "(No header)"
                label = f"Table {i+1}: {header}"
                if any(x in header.lower() for x in ["balance sheet", "income statement"]):
                    label += " (PRIORITY TABLE)"
                prompt += label + "\n"
                for row in rows:
                    prompt += ' | '.join([cell.strip() for cell in row.split(',')]) + '\n'
                prompt += '\n'
    prompt += (
        f"Recent News:\n{news}\n\n"
        "Instructions: Carefully extract and compare the following financial metrics from the 10-Q filings: "
        "Revenue, Gross Margin, Net Income, Cost of Goods Sold (COGS), Cost of Sales, Debt to Equity Ratio, and Liquidity Ratio. "
        "If any metric is not available, leave the cell blank or mark as 'Not Provided'. "
        "Build a summary table with columns for each filing/quarter and rows for each metric above. "
        "The table should be in markdown format, with each column representing a quarter/filing and each row a metric. "
        "Prioritize analysis of Balance Sheet and Income Statement tables from Item 1, and layer in the MD&A and Notes from Item 2. "
        "After the table, provide a narrative analysis of trends, changes, and any notable risks or opportunities. "
        "Only output valid JSON. Respond in the following JSON format:\n"
        "{\n  \"financial_summary\": \"...\",\n  \"key_metrics_table\": \"...\",\n  \"suggested_graph\": \"...\",\n  \"recent_events_summary\": \"...\",\n  \"questions_to_ask\": [\"...\", \"...\"]\n}\n"
    )
    if extraction_notes:
        prompt += f"\n\nExtraction Notes: {'; '.join(extraction_notes)}"
    max_prompt_tokens = 20000
    prompt_token_count = count_tokens(prompt)
    if prompt_token_count > max_prompt_tokens:
        logger.warning(f"Prompt too large ({prompt_token_count} tokens). Truncating to {max_prompt_tokens} tokens.")
        prompt = safe_truncate_prompt(prompt, max_prompt_tokens)
    return prompt

def fetch_google_company_signals(company_name: str) -> str:
    """
    Fetch recent company news using Google Custom Search as a fallback enrichment source.
    Returns a string of formatted news results or an error message.
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
    """
    Remove markdown code block markers and whitespace from LLM output, returning clean JSON string.
    """
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

def extract_metrics_from_html_tables(html_tables: list) -> tuple:
    """
    Attempt to extract required metrics from HTML tables using pandas.
    Returns a tuple: (metrics_data: dict, metrics_found: set)
    """
    metrics_found = set()
    metrics_data = {}
    for table_html in html_tables:
        try:
            dfs = pd.read_html(table_html)
        except Exception as e:
            logger.warning(f"Error reading HTML table with pandas: {e}", exc_info=True)
            continue
        for df in dfs:
            # Modularized: Extract metrics from DataFrame
            _extract_metrics_from_df(df, metrics_data, metrics_found)
        # If we found all metrics, break early
        if len(metrics_found) == len(REQUIRED_METRICS):
            break
    return metrics_data, metrics_found

def _extract_metrics_from_df(df, metrics_data: dict, metrics_found: set) -> None:
    """
    Extract required metrics from a pandas DataFrame and update metrics_data and metrics_found.
    """
    try:
        for metric in REQUIRED_METRICS:
            for col in df.columns:
                if metric.lower() in str(col).lower():
                    metrics_found.add(metric)
                    for idx, row in df.iterrows():
                        for c in df.columns:
                            if metric.lower() in str(c).lower():
                                val = row[c]
                                quarter = str(row[0]) if df.columns[0] != c else f"Row {idx+1}"
                                if quarter not in metrics_data:
                                    metrics_data[quarter] = {}
                                metrics_data[quarter][metric] = str(val)
    except Exception as e:
        logger.warning(f"Error extracting metrics from DataFrame: {e}", exc_info=True)

def _truncate_extracted_sections(sections: dict, max_tokens: int, logger) -> dict:
    """
    Truncate extracted sections (item1, item2, notes) to fit within max_tokens.
    Returns a new dict and a list of truncation notes.
    """
    from copy import deepcopy
    truncated = deepcopy(sections)
    truncation_notes = []
    total_tokens = 0
    for key in ["item1", "item2", "notes"]:
        text = truncated.get(key, "")
        tokens = count_tokens(text)
        if total_tokens + tokens > max_tokens:
            allowed = max_tokens - total_tokens
            if allowed > 0:
                text = safe_truncate_prompt(text, allowed)
                truncation_notes.append(f"{key} truncated to fit token budget.")
                tokens = count_tokens(text)
            else:
                text = ""
                truncation_notes.append(f"{key} omitted due to token budget.")
                tokens = 0
        truncated[key] = text
        total_tokens += tokens
    truncated["truncation_notes"] = truncation_notes
    return truncated

def analyze_financials(extracted_data: dict, additional_context: dict = None) -> Dict[str, Any]:
    """
    Agent 2: Analyze extracted 10-Q sections and tables, build metrics table, and provide analysis.
    Expects a dict with keys: item1, item2, notes, item1_tables, etc.
    Returns a dict with financial analysis or error, and always includes raw_tables.
    """
    logger.info("Starting analyze_financials for extracted data.")
    try:
        # Validate input
        if not extracted_data or not isinstance(extracted_data, dict):
            logger.error("No extracted data provided to Agent 2.")
            return {"error": "No extracted data provided to Agent 2.", "notes": [], "stage": "input_validation", "raw_tables": []}
        item1 = extracted_data.get("item1", "")
        item2 = extracted_data.get("item2", "")
        notes = extracted_data.get("notes", "")
        item1_tables = extracted_data.get("item1_tables", [])
        extraction_notes = extracted_data.get("extraction_notes", [])
        all_raw_tables = []
        # --- Try Python table extraction ---
        python_metrics = {}
        python_metrics_found = set()
        metrics, found = extract_metrics_from_html_tables(item1_tables)
        if metrics:
            python_metrics.update(metrics)
        python_metrics_found.update(found)
        # --- Collect all tables for this filing ---
        filing_tables = []
        for table in item1_tables:
            rows = [row.split(',') for row in table.split('\n') if row.strip()]
            filing_tables.append(rows)
        all_raw_tables.append({
            "tables": filing_tables
        })
        # --- If all required metrics found, use Python extraction ---
        if python_metrics and len(python_metrics_found) == len(REQUIRED_METRICS):
            extraction_notes.append("All required metrics extracted via Python table parsing.")
            normalized_table = normalize_key_metrics_table(python_metrics)
            logger.info("All required metrics extracted via Python table parsing.")
            return {
                "financial_summary": "Extracted all key metrics using Python table parsing.",
                "recent_events_summary": "",
                "key_metrics_table": normalized_table,
                "suggested_graph": "",
                "questions_to_ask": [],
                "notes": extraction_notes,
                "source": "python",
                "raw_tables": all_raw_tables
            }
        # --- Otherwise, fallback to LLM/RAG as before ---
        if not item1 and not item2:
            logger.error("No valid extracted sections could be processed.")
            return {"error": "No valid extracted sections could be processed.", "notes": extraction_notes, "stage": "extract_validation", "raw_tables": all_raw_tables}
        # --- Token count and soft truncation logic ---
        extraction_payload = {
            "item1": item1,
            "item2": item2,
            "notes": notes,
            "item1_tables": item1_tables
        }
        total_tokens = count_tokens(item1) + count_tokens(item2) + count_tokens(notes)
        logger.info(f"[Agent2] Extraction payload token count: {total_tokens}")
        truncation_notes = []
        if total_tokens > GROQ_SOFT_EXTRACTION_TOKEN_LIMIT:
            logger.warning(f"[Agent2] Extraction payload exceeds soft token limit ({GROQ_SOFT_EXTRACTION_TOKEN_LIMIT}). Truncating sections.")
            extraction_payload = _truncate_extracted_sections(extraction_payload, GROQ_SOFT_EXTRACTION_TOKEN_LIMIT, logger)
            truncation_notes = extraction_payload.get("truncation_notes", [])
        # Always use Google Custom Search for news enrichment
        external_signals = _get_external_signals("")  # Company name not available here
        # --- Add user context to the prompt ---
        ac = additional_context or {}
        user_context_section = (
            "User-provided meeting context (pre-meeting):\n"
            f"- First meeting: {ac.get('first_meeting', 'Not specified')}\n"
            f"- User knowledge: {ac.get('user_knowledge', 'Not specified')}\n"
            f"- Proposed solutions: {ac.get('proposed_solutions', 'Not specified')}\n"
            f"- Wants messaging help: {ac.get('messaging_help', 'Not specified')}\n\n"
        )
        # Build prompt from extracted sections
        prompt = user_context_section + build_groq_prompt_from_filings("", [{
            "item1": extraction_payload["item1"],
            "item2": extraction_payload["item2"],
            "notes": extraction_payload["notes"],
            "item1_tables": extraction_payload["item1_tables"]
        }], external_signals, extraction_notes + truncation_notes)
        prompt_token_count = count_tokens(prompt)
        logger.info(f"Prompt token count: {prompt_token_count}")
        if prompt_token_count > GROQ_SAFE_PROMPT_TOKENS:
            extraction_notes.append(f"Prompt was truncated from {prompt_token_count} tokens to {GROQ_SAFE_PROMPT_TOKENS} tokens.")
            prompt = safe_truncate_prompt(prompt, GROQ_SAFE_PROMPT_TOKENS)
        # --- Refactored: LLM fallback analysis ---
        llm_result = _llm_fallback_analysis(prompt, extraction_notes)
        if "error" in llm_result:
            logger.error("LLM fallback analysis failed: %s", llm_result["error"])
            return {**llm_result, "raw_tables": all_raw_tables}
        # --- Refactored: Output normalization ---
        normalized_output = _normalize_llm_output(llm_result, extraction_notes, "")
        normalized_output["raw_tables"] = all_raw_tables
        return normalized_output
    except Exception as e:
        logger.error(f"Agent 2 - Financial analysis failed: {e}", exc_info=True)
        return {
            "financial_summary": f"Agent 2 - Financial analysis failed: {str(e)}",
            "key_metrics_table": {},
            "recent_events_summary": "",
            "suggested_graph": "",
            "questions_to_ask": [],
            "notes": [],
            "stage": "analyze_financials_exception",
            "raw_tables": []
        }

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

def _llm_fallback_analysis(prompt: str, extraction_notes: list) -> dict:
    """
    Helper to call the LLM for financial analysis. Returns dict with LLM output or error structure.
    """
    try:
        result = call_groq(
            prompt,
            max_tokens=32768,
            include_domains=["sec.gov"],
            response_format={"type": "json_object"}
        )
        logger.info("Agent 2 Groq raw output: %s", result)
        return {"llm_output": result}
    except Exception as e:
        logger.error(f"Agent 2 - Financial analysis failed: {e}", exc_info=True)
        extraction_notes.append(f"Agent 2 - Financial analysis failed: {str(e)}")
        return {"error": f"Agent 2 - Financial analysis failed: {str(e)}", "notes": extraction_notes, "stage": "llm_fallback_analysis"}

def _normalize_llm_output(llm_result: dict, extraction_notes: list, company_name: str) -> dict:
    """
    Helper to parse and normalize LLM output, ensuring correct types and fallback messaging.
    Returns the final output dict for the API.
    """
    try:
        result = llm_result.get("llm_output")
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
                    return {"error": f"Groq output was not valid JSON and could not be fixed: {str(e2)}", "notes": extraction_notes, "stage": "normalize_llm_output"}
            else:
                try:
                    fixed = clean_result.replace(",]", "]").replace(",}}", "}}")
                    parsed = json.loads(fixed)
                except Exception as e2:
                    logger.error(f"Failed to fix Groq output: {e2}")
                    return {"error": f"Groq output was not valid JSON and could not be fixed: {str(e2)}", "notes": extraction_notes, "stage": "normalize_llm_output"}
        # Fallback messaging if no real data
        if not parsed or not any(parsed.get(k) for k in ["financial_summary", "key_metrics_table", "recent_events_summary"]):
            logger.warning("No financial data found in filings for company: %s", company_name)
            return {
                "financial_summary": "No financial data found in filings. Please check the filings manually.",
                "key_metrics_table": {},
                "suggested_graph": "",
                "recent_events_summary": "",
                "questions_to_ask": [],
                "notes": extraction_notes,
                "stage": "normalize_llm_output"
            }
        # --- Ensure correct types for output fields ---
        key_metrics_table = parsed.get("key_metrics_table", {})
        def dict_to_list_of_strings(d):
            return [f"{k}: {v}" for k, v in d.items()]
        if isinstance(key_metrics_table, dict):
            for k, v in list(key_metrics_table.items()):
                if isinstance(v, dict):
                    key_metrics_table[k] = dict_to_list_of_strings(v)
                elif isinstance(v, str):
                    key_metrics_table[k] = [v]
                elif isinstance(v, list):
                    key_metrics_table[k] = [str(x) for x in v]
                else:
                    key_metrics_table[k] = [str(v)]
        else:
            key_metrics_table = {}
        normalized_table = normalize_key_metrics_table(parsed.get("key_metrics_table", {}))
        questions_to_ask = parsed.get("questions_to_ask", [])
        if not isinstance(questions_to_ask, list):
            questions_to_ask = [str(questions_to_ask)] if questions_to_ask else []
        suggested_graph = ""
        json_payload_for_agents_3_4 = {
            "company_name": company_name,
            "financial_summary": parsed.get("financial_summary", "") if parsed else "",
            "recent_events_summary": parsed.get("recent_events_summary", "") if parsed else "",
            "key_metrics_table": normalized_table,
            "suggested_graph": suggested_graph,
            "questions_to_ask": questions_to_ask,
            "notes": extraction_notes
        }
        return json_payload_for_agents_3_4
    except Exception as e:
        logger.error(f"Failed to normalize LLM output: {e}", exc_info=True)
        return {
            "error": f"Failed to normalize LLM output: {str(e)}",
            "notes": extraction_notes,
            "stage": "normalize_llm_output_exception"
        }

def _get_external_signals(company_name: str) -> str:
    """
    Helper to get external news/signals for a company. Tries Google Custom Search first, then falls back to synthetic signals.
    Returns a string with news/signals, or a clear error message.
    """
    logger.info("Fetching external signals for company: %s", company_name)
    try:
        signals = fetch_google_company_signals(company_name)
        if not signals or 'No public web results found.' in signals or 'API key' in signals:
            logger.warning("Google Custom Search did not return results or API key missing for company: %s. Falling back to synthetic signals.", company_name)
            signals = generate_synthetic_signals(company_name)
        if not signals:
            logger.error("No external signals (news or synthetic) could be generated for company: %s", company_name)
            return "No external signals available."
        return signals
    except Exception as e:
        logger.error(f"Failed to fetch or generate external signals for {company_name}: {e}", exc_info=True)
        return f"Failed to fetch or generate external signals: {str(e)}"
