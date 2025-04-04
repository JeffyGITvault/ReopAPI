from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
import re

from cik_resolver import resolve_cik, NEW_ALIASES, push_new_aliases_to_github

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-Q for viewing and 10-K for Excel download. Uses dynamic CIK resolution, alias mapping, and fallback logic.",
    version="v4.2.0"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

# === Utility ===
def validate_url(url):
    try:
        resp = requests.head(url, headers=HEADERS)
        return resp.status_code == 200
    except:
        return False

def get_actual_filing_urls(cik, accession, primary_doc):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"
    report_url = base_url + primary_doc if primary_doc and primary_doc.endswith(".htm") else None
    excel_url = None

    resp = requests.get(index_url, headers=HEADERS)
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        found_excel_files = []
        for a in soup.find_all("a"):
            href = a.get("href", "").lower()
            if not href:
                continue
            full_url = f"https://www.sec.gov{href}"
            if not report_url and href.endswith(".htm") and ("10q" in href or "10-k" in href):
                report_url = full_url
            if href.endswith(".xlsx") and "financial" in href:
                found_excel_files.append(full_url)

        for url in found_excel_files:
            if validate_url(url):
                excel_url = url
                break

    return {
        "10-K/10-Q Index Page": index_url,
        "Full HTML Filing Report": report_url,
        "Financial Report (Excel)": excel_url
    }

def get_latest_filing(cik, form_type):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        return None, None

    data = response.json()
    filings = data.get("filings", {}).get("recent", {})
    form_types = filings.get("form", [])
    accession_numbers = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [])
    filing_dates = filings.get("filingDate", [])

    cutoff = datetime.now() - timedelta(days=5*365)

    for i, form in enumerate(form_types):
        try:
            filing_date = datetime.strptime(filing_dates[i], "%Y-%m-%d")
            if filing_date < cutoff:
                continue
            if form == form_type:
                accession = accession_numbers[i].replace("-", "")
                return accession, primary_docs[i]
        except:
            continue
    return None, None

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    cik, matched_name = resolve_cik(company_name)
    if not cik:
        return {"error": f"Unable to resolve CIK for {company_name}"}

    q_accession, q_primary_doc = get_latest_filing(cik, "10-Q")
    k_accession, k_primary_doc = get_latest_filing(cik, "10-K")

    q_urls = get_actual_filing_urls(cik, q_accession, q_primary_doc) if q_accession else {}
    k_urls = get_actual_filing_urls(cik, k_accession, k_primary_doc) if k_accession else {}

    push_new_aliases_to_github()  # Attempt alias push after resolution

    return {
        "Matched Company Name": matched_name,
        "CIK": cik,
        "10-Q Filing": q_urls if q_urls else "No recent 10-Q found",
        "10-K Excel": k_urls.get("Financial Report (Excel)") if k_urls else "No recent 10-K Excel found"
    }
