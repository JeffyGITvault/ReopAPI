# app/api/agents/agent1_fetch_sec.py

from app.api.SECAPI import get_quarterly_filings
from app.api.cik_resolver import load_alias_map
from fastapi import Request
from starlette.requests import Request as StarletteRequest

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
