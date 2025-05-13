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
    Returns a dict with a list of SEC filing metadata (date, url, title, etc.) or an error message.
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
            # Estimate token count for logging, but do not chunk or parse
            if html_url and html_url != "Unavailable":
                try:
                    html = fetch_10q_html(html_url)
                    text = clean_and_extract_text(html)
                    estimated_tokens = estimate_token_count(text)
                except Exception as e:
                    logger.warning(f"Token estimate failed for {html_url}: {e}")
            filings_list.append({
                "filing_date": filing.get("filing_date"),
                "html_url": html_url,
                "title": filings_data.get("company_name", company_name),
                "marker": filing.get("marker", ""),
                "estimated_tokens": estimated_tokens
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
