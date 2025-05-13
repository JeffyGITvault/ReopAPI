# app/api/agents/agent1_fetch_sec.py

import logging
from typing import Dict, Any, List
from app.api.SECAPI import get_quarterly_filings
from app.api.cik_resolver import load_alias_map
from fastapi import Request
from starlette.requests import Request as StarletteRequest
import requests
from bs4 import BeautifulSoup
from app.api.config import DEFAULT_HEADERS
import os
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# === Caching Config ===
CACHE_SIZE = int(os.getenv("AGENT1_CACHE_SIZE", 20))
CACHE_TTL = int(os.getenv("AGENT1_CACHE_TTL", 3600))  # seconds
_html_cache = TTLCache(maxsize=CACHE_SIZE, ttl=CACHE_TTL)
_meta_cache = TTLCache(maxsize=CACHE_SIZE, ttl=CACHE_TTL)

class DummyRequest(StarletteRequest):
    def __init__(self):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
        }
        super().__init__(scope)

def fetch_10q(company_name: str, count: int = 2) -> Dict[str, Any]:
    """
    Agent 1: Fetch the latest N 10-Q filings for a given company.
    Returns a dict with a list of SEC filing metadata (date, url, title, extracted sections, etc.) or an error message.
    Uses caching for metadata results.
    """
    cache_key = f"{company_name.lower().strip()}_{count}"
    if cache_key in _meta_cache:
        logger.info(f"[Agent1] Cache hit for metadata: {cache_key}")
        return _meta_cache[cache_key]
    try:
        dummy_request = DummyRequest()
        filings_data = get_quarterly_filings(
            request=dummy_request,
            company_name=company_name,
            count=count
        )
        filings = filings_data.get("filings", [])
        filings_list = []
        for filing in filings:
            html_url = filing.get("html_url")
            estimated_tokens = None
            extracted_sections = None
            extraction_notes = []
            # Estimate token count for logging, and extract sections
            if html_url and html_url != "Unavailable":
                try:
                    html = fetch_10q_html(html_url)
                    text = clean_and_extract_text(html)
                    estimated_tokens = estimate_token_count(text)
                    # New: extract sections
                    extracted_sections = extract_10q_sections(html, extraction_notes)
                except Exception as e:
                    logger.warning(f"Token estimate or extraction failed for {html_url}: {e}")
            filings_list.append({
                "filing_date": filing.get("filing_date"),
                "html_url": html_url,
                "title": filings_data.get("company_name", company_name),
                "marker": filing.get("marker", ""),
                "estimated_tokens": estimated_tokens,
                "extracted_sections": extracted_sections,
                "extraction_notes": extraction_notes
            })
        result = {
            "company_name": filings_data.get("company_name", company_name),
            "cik": filings_data.get("cik"),
            "filings": filings_list
        }
        _meta_cache[cache_key] = result
        return result
    except Exception as e:
        logger.error(f"Agent 1 - SEC data fetch failed: {e}")
        return {"error": f"Agent 1 - SEC data fetch failed: {str(e)}"}

def fetch_10q_html(url: str) -> str:
    """
    Fetch the HTML content of a 10-Q filing from a given URL, using cache if available.
    """
    if url in _html_cache:
        logger.info(f"[Agent1] Cache hit for HTML: {url}")
        return _html_cache[url]
    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
        response.raise_for_status()
        html = response.text
        _html_cache[url] = html
        return html
    except Exception as e:
        logger.error(f"Failed to fetch 10-Q HTML: {e}")
        raise Exception(f"Failed to fetch 10-Q HTML: {str(e)}")

def clean_and_extract_text(html: str) -> str:
    """
    Clean and extract text from HTML, removing scripts and styles.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n")

def estimate_token_count(text: str) -> int:
    """
    Estimate the number of tokens in a text (approximate for LLMs).
    """
    words = len(text.split())
    return int(words / 0.75)

# --- Extraction logic moved from Agent 2 ---
def extract_10q_sections(html: str, extraction_notes: list) -> dict:
    """
    Extract Item 1 (Financial Statements), Item 2 (MD&A), and relevant Notes from 10-Q HTML/text.
    Returns a dict with 'item1', 'item2', 'notes', and 'item1_tables' keys.
    """
    from bs4 import BeautifulSoup
    import re
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
    from bs4 import BeautifulSoup
    import re
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
    import re
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
