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
    Extracts all Parts (I, II, etc.) and their Items from 10-Q HTML/text.
    Always keys the result as "Part I", "Part II", etc. (Roman numerals).
    """
    from bs4 import BeautifulSoup
    import re

    def estimate_tokens(text: str) -> int:
        words = len(text.split())
        return int(words / 0.75)

    def arabic_to_roman(num):
        mapping = {
            '1': 'I', '2': 'II', '3': 'III', '4': 'IV', '5': 'V',
            '6': 'VI', '7': 'VII', '8': 'VIII', '9': 'IX', '10': 'X'
        }
        return mapping.get(str(num), str(num))

    soup = BeautifulSoup(html, "html.parser")
    raw = soup.get_text(separator=" ")
    norm = " ".join(raw.split())

    # Match both Roman and Arabic numerals for "Part"
    part_hdrs = list(re.finditer(r'(Part\s+((?:[IVX]+)|(?:\d+)))\.?', norm, re.IGNORECASE))
    parts = []
    for idx, m in enumerate(part_hdrs):
        start = m.start()
        end = part_hdrs[idx+1].start() if idx+1 < len(part_hdrs) else len(norm)
        numeral = m.group(2)
        # Convert Arabic to Roman if needed
        if numeral.isdigit():
            roman = arabic_to_roman(numeral)
        else:
            roman = numeral.upper()
        key = f"Part {roman}"
        parts.append((key, norm[start:end]))

    result = {}
    for key, part_text in parts:
        items = {}
        item_hdrs = list(re.finditer(r'(Item\s*\d+[A-Za-z]?\.)(?=\s)', part_text, re.IGNORECASE))
        for i, ih in enumerate(item_hdrs):
            istart = ih.start()
            iend = item_hdrs[i+1].start() if i+1 < len(item_hdrs) else len(part_text)
            title = ih.group(1).strip()
            body = part_text[istart:iend].strip()
            # Pull out tables from the raw HTML slice
            html_slice = html[ html.lower().find(title.lower()) : ]
            next_item = re.search(r'Item\s*\d+[A-Za-z]?\.', html_slice, re.IGNORECASE)
            html_slice = html_slice[: next_item.start() ] if next_item else html_slice
            tsoup = BeautifulSoup(html_slice, "html.parser")
            tables = []
            for tbl in tsoup.find_all("table"):
                rows = []
                for tr in tbl.find_all("tr"):
                    cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td","th"])]
                    rows.append(",".join(cells))
                text_tbl = "\n".join(rows).strip()
                if text_tbl:
                    tables.append(text_tbl)
            items[title] = {
                "text":   body,
                "tables": tables,
                "tokens": estimate_tokens(body)
            }
        total = sum(v["tokens"] for v in items.values())
        result[key] = {
            "total_tokens": total,
            "items":        items
        }
        extraction_notes.append(f"{key}: {total} tokens across {len(items)} items")
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
