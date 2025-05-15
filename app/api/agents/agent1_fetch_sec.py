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
import re

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

def extract_10q_sections(html: str, extraction_notes: list) -> dict:
    """
    Extract all Parts (I, II, etc.) and their Items from 10-Q HTML/text.
    For each item, extract text, tables, and token count.
    Returns a nested dict: { "Part I": { "total_tokens": int, "items": { "Item 1.": {...}, ... } }, ... }
    """
    from bs4 import BeautifulSoup
    import re

    def estimate_token_count(text: str) -> int:
        words = len(text.split())
        return int(words / 0.75)

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    norm = ' '.join(text.split())

    # Find all "Part I", "Part II", etc.
    part_matches = list(re.finditer(r'(Part\s+[IVX]+\.?)', norm, re.IGNORECASE))
    part_spans = []
    for idx, match in enumerate(part_matches):
        start = match.start()
        end = part_matches[idx + 1].start() if idx + 1 < len(part_matches) else len(norm)
        part_spans.append((match.group(1).strip(), start, end))

    result = {}
    for part_name, start, end in part_spans:
        part_text = norm[start:end]
        # Find all "Item X." headers in this part
        item_matches = list(re.finditer(r'(Item\s*\d+[A-Za-z]?\.)(?=\s)', part_text, re.IGNORECASE))
        items = {}
        for idx, item_match in enumerate(item_matches):
            item_start = item_match.start()
            item_end = item_matches[idx + 1].start() if idx + 1 < len(item_matches) else len(part_text)
            item_title = item_match.group(1).strip()
            item_body = part_text[item_start:item_end].strip()
            # Extract tables from the original HTML for this item
            html_item_match = re.search(re.escape(item_title), html, re.IGNORECASE)
            if html_item_match:
                html_item_start = html_item_match.start()
                html_item_end = html.find("Item", html_item_start + 1)
                html_item = html[html_item_start:html_item_end] if html_item_end != -1 else html[html_item_start:]
                item_soup = BeautifulSoup(html_item, "html.parser")
                tables = []
                for table in item_soup.find_all('table'):
                    rows = []
                    for tr in table.find_all('tr'):
                        cells = [td.get_text(separator=" ", strip=True) for td in tr.find_all(['td', 'th'])]
                        rows.append(','.join(cells))
                    table_text = '\n'.join(rows)
                    if table_text.strip():
                        tables.append(table_text)
            else:
                tables = []
            items[item_title] = {
                "text": item_body,
                "tables": tables,
                "tokens": estimate_token_count(item_body)
            }
        part_total_tokens = sum(item["tokens"] for item in items.values())
        result[part_name] = {
            "total_tokens": part_total_tokens,
            "items": items
        }
        extraction_notes.append(f"{part_name}: {part_total_tokens} tokens, {len(items)} items extracted.")

    # Log the token counts for each part and item
    for part, pdata in result.items():
        logger.info(f"[Token Budget] {part}: {pdata['total_tokens']} tokens")
        for item, idata in pdata["items"].items():
            logger.info(f"  - {item}: {idata['tokens']} tokens")

    return result

def normalize_part_key(s):
    """
    Normalize part keys to a canonical form: 'part1', 'part2', etc.
    Handles case, whitespace, periods, and roman numerals.
    """
    s = s.lower().replace('.', '').replace(' ', '')
    # Convert roman numerals to arabic numerals at the end of the string
    roman_map = {
        'x': '10', 'ix': '9', 'viii': '8', 'vii': '7', 'vi': '6',
        'v': '5', 'iv': '4', 'iii': '3', 'ii': '2', 'i': '1'
    }
    for roman, arabic in sorted(roman_map.items(), key=lambda x: -len(x[0])):  # longest first
        if s.endswith(roman):
            s = s[:-len(roman)] + arabic
            break
    return s

def find_part_key(extracted, part_name):
    norm_part = normalize_part_key(part_name)
    for k in extracted:
        if normalize_part_key(k) == norm_part:
            return k
    return None
