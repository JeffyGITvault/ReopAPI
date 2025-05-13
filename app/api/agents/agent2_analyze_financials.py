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

REQUIRED_METRICS = [
    "Revenue",
    "Gross Margin",
    "Net Income",
    "Cost of Goods Sold",
    "Cost of Sales",
    "Days Sales Outstanding (DSO)",
    "Days Payable Outstanding (DPO)",
    "Debt to Equity Ratio",
    "Liquidity Ratio"
]

def normalize_key_metrics_table(table):
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
        "Revenue, Gross Margin, Net Income, Cost of Goods Sold (COGS) or Cost of Sales, Days Sales Outstanding (DSO), Days Payable Outstanding (DPO), Debt to Equity Ratio, and Liquidity Ratio. "
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

def extract_metrics_from_html_tables(html_tables):
    """
    Attempt to extract required metrics from HTML tables using pandas.
    Returns a dict of {quarter: {metric: value, ...}} and a set of found metrics.
    """
    metrics_found = set()
    metrics_data = {}
    for table_html in html_tables:
        try:
            dfs = pd.read_html(table_html)
        except Exception:
            continue
        for df in dfs:
            # Try to find columns that match required metrics
            for metric in REQUIRED_METRICS:
                for col in df.columns:
                    if metric.lower() in str(col).lower():
                        metrics_found.add(metric)
                        # Try to extract values for each quarter (columns or rows)
                        for idx, row in df.iterrows():
                            for c in df.columns:
                                if metric.lower() in str(c).lower():
                                    val = row[c]
                                    # Use index or a column as quarter label
                                    quarter = str(row[0]) if df.columns[0] != c else f"Row {idx+1}"
                                    if quarter not in metrics_data:
                                        metrics_data[quarter] = {}
                                    metrics_data[quarter][metric] = str(val)
        # If we found all metrics, break early
        if len(metrics_found) == len(REQUIRED_METRICS):
            break
    return metrics_data, metrics_found

def analyze_financials(sec_data: dict, additional_context: dict = None) -> Dict[str, Any]:
    """
    Agent 2: Analyze financials from SEC data, fetch news signals, and with LLM.
    Returns a dict with financial analysis or error.
    """
    logger.info("Starting analyze_financials for company: %s", sec_data.get("company_name", "Unknown"))
    try:
        company_name = sec_data.get("company_name", "the company")
        filings = sec_data.get("filings", [])
        if not filings:
            logger.error("No 10-Q filings found for financial analysis. Company: %s", company_name)
            return {"error": "No 10-Q filings found for financial analysis.", "notes": [], "stage": "fetch_filings"}
        # --- Refactored: Fetch and extract filings ---
        filings_result = _fetch_and_extract_filings(filings, company_name)
        if "error" in filings_result:
            logger.error("Error in _fetch_and_extract_filings: %s", filings_result["error"])
            return filings_result
        extracted_filings = filings_result["extracted_filings"]
        extraction_notes = filings_result["extraction_notes"]
        python_metrics = filings_result["python_metrics"]
        python_metrics_found = filings_result["python_metrics_found"]
        missing_filings = filings_result["missing_filings"]
        # --- If all required metrics found, use Python extraction ---
        if python_metrics and len(python_metrics_found) == len(REQUIRED_METRICS):
            extraction_notes.append("All required metrics extracted via Python table parsing.")
            normalized_table = normalize_key_metrics_table(python_metrics)
            logger.info("All required metrics extracted via Python table parsing for company: %s", company_name)
            return {
                "company_name": company_name,
                "financial_summary": "Extracted all key metrics using Python table parsing.",
                "recent_events_summary": "",
                "key_metrics_table": normalized_table,
                "suggested_graph": "",
                "questions_to_ask": [],
                "notes": extraction_notes,
                "source": "python"
            }
        # --- Otherwise, fallback to LLM/RAG as before ---
        if not extracted_filings:
            logger.error("No valid 10-Q filings could be processed for company: %s", company_name)
            return {"error": "No valid 10-Q filings could be processed.", "notes": extraction_notes, "stage": "fetch_and_extract_filings"}
        if missing_filings:
            extraction_notes.append(f"{missing_filings} filings could not be processed and were skipped.")
        # Always use Google Custom Search for news enrichment
        external_signals = _get_external_signals(company_name)
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
        # --- Refactored: LLM fallback analysis ---
        llm_result = _llm_fallback_analysis(prompt, extraction_notes)
        if "error" in llm_result:
            logger.error("LLM fallback analysis failed: %s", llm_result["error"])
            return llm_result
        # --- Refactored: Output normalization ---
        normalized_output = _normalize_llm_output(llm_result, extraction_notes, company_name)
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
            "stage": "analyze_financials_exception"
        }

def _fetch_and_extract_filings(filings: list, company_name: str) -> dict:
    """
    Helper to fetch and extract 10-Q filings, returning extracted sections, notes, and metrics.
    Returns a dict with keys: extracted_filings, extraction_notes, python_metrics, python_metrics_found, missing_filings.
    Returns {"error": ..., "notes": [...], "stage": ...} on error.
    """
    logger.info("Fetching and extracting %d filings for company: %s", len(filings), company_name)
    extracted_filings = []
    missing_filings = 0
    extraction_notes = []
    python_metrics = {}
    python_metrics_found = set()
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
            # --- Try Python table extraction ---
            html_tables = extracted.get("item1_tables", [])
            metrics, found = extract_metrics_from_html_tables(html_tables)
            if metrics:
                python_metrics.update(metrics)
            python_metrics_found.update(found)
        except Exception as e:
            logger.warning(f"Failed to fetch or extract filing at {url}: {e}", exc_info=True)
            extraction_notes.append(f"Failed to fetch or extract filing at {url}: {e}")
            missing_filings += 1
    if not extracted_filings:
        logger.error("No valid 10-Q filings could be processed for company: %s", company_name)
        return {"error": "No valid 10-Q filings could be processed.", "notes": extraction_notes, "stage": "fetch_and_extract_filings"}
    return {
        "extracted_filings": extracted_filings,
        "extraction_notes": extraction_notes,
        "python_metrics": python_metrics,
        "python_metrics_found": python_metrics_found,
        "missing_filings": missing_filings
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
