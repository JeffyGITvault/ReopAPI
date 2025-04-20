# === Standard Library ===
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# === Third-Party Libraries ===
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

# === Local Modules ===
from cik_resolver import resolve_company_name, push_new_aliases_to_github
from utils import get_actual_filing_urls

app = FastAPI(
    title="SECAPI",
    version="4.3.4",
    description="API to retrieve SEC 10-Q filings with GPT/agent support"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
MAX_PARALLEL = 10

# Enable CORS for external use
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "SECAPI is live"}

@app.get("/get_quarterlies/{company_name}")
def get_quarterlies(
    company_name: str = Path(..., description="Company name or stock ticker"),
    agent_mode: Optional[bool] = Query(False, description="Return 4 filings instead of 2")
):
    start_time = time.time()

    try:
        resolved_name, cik = resolve_company_name(company_name)
    except Exception as e:
        return {
            "error": f"Could not resolve company name: {company_name}",
            "details": str(e)
        }

    try:
        filings = get_actual_filing_urls(cik, form_type="10-Q")
        sorted_filings = sorted(filings, key=lambda x: x.get("filing_date", ""), reverse=True)
        top_four = sorted_filings[:4]

        primary = top_four[:2]
        cached = top_four[2:] if agent_mode else []

        for i, report in enumerate(primary, start=1):
            report["DisplayIndex"] = str(i)
            report["Marker"] = "📌 Most Recent" if i == 1 else "🕓 Older"

        print(f"[DEBUG] First filing: {repr(primary[0]) if primary else 'None'}")
        print(f"[TIMING] Total duration: {round(time.time() - start_time, 2)}s for {company_name}")

        try:
            push_new_aliases_to_github()
        except Exception as e:
            print(f"[Warning] Alias push failed: {e}")

        return {
            "company_name": resolved_name,
            "cik": cik,
            "quarterly_reports": primary,
            "cached_quarterlies": cached
        }

    except Exception as e:
        return {
            "error": f"Could not fetch 10-Q filings for CIK: {cik}",
            "details": str(e)
        }
