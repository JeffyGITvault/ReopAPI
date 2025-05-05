# app/api/agents/agent1_fetch_sec.py

from app.api.SECAPI import get_quarterly_filings
from app.api.cik_resolver import load_alias_map
from fastapi import Request
from starlette.requests import Request as StarletteRequest

import requests
from bs4 import BeautifulSoup

class DummyRequest(StarletteRequest):
    def __init__(self):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
        }
        super().__init__(scope)

def fetch_10q(company_name: str) -> dict:
    """
    Agent 1: Fetch the latest 10-Q filings for a given company.
    """
    try:
        dummy_request = DummyRequest()
        filings_data = get_quarterly_filings(
            request=dummy_request,
            company_name=company_name,
            count=2
        )
        return filings_data

    except Exception as e:
        return {"error": f"Agent 1 - SEC data fetch failed: {str(e)}"}

def fetch_10q_html(url: str) -> str:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        raise Exception(f"Failed to fetch 10-Q HTML: {str(e)}")

def clean_and_extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n")

def estimate_token_count(text: str) -> int:
    words = len(text.split())
    return int(words / 0.75)

def chunk_10q_text(text: str, chunk_size=10000, overlap=1000) -> dict:
    try:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-3-70b")
        tokens = tokenizer.encode(text)
        chunks = []

        for i in range(0, len(tokens), chunk_size - overlap):
            chunk_tokens = tokens[i:i + chunk_size]
            chunk_text = tokenizer.decode(chunk_tokens)
            chunks.append(chunk_text)

        return {"source": "html", "chunks": chunks, "total_tokens": len(tokens)}
    except Exception as e:
        return {"error": f"Tokenization failed: {str(e)}"}

def parse_10q_from_url(url: str) -> dict:
    html = fetch_10q_html(url)
    text = clean_and_extract_text(html)
    estimated_tokens = estimate_token_count(text)

    if estimated_tokens < 30000:
        return chunk_10q_text(text)
    else:
        return {"source": "url", "url": url, "estimated_tokens": estimated_tokens}
