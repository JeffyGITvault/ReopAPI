from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime, timedelta
from cik_resolver import resolve_cik, push_new_aliases_to_github

app = FastAPI(
    title="Get SEC Filings Data",
    description="Fetches the latest 10-Q and 10-K filings, prioritizing HTML documents with Excel as a fallback. Uses CIK resolution, alias mapping, and GitHub-based alias updates.",
    version="v4.2.5"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

# === Utilities ===
def validate_url(url):
    try:
        resp = requests.head(url, headers=HEADERS)
        return resp.status_code == 200
    except:
        return False

def get_actual_filing_urls(cik, accession, primary_doc, form_type):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"
    html_url = None
    excel_url = None

    try:
        # Always try to use the primary document first
        if primary_doc and primary_doc.endswith(".htm"):
            candidate = base_url + primary_doc
            if validate_url(candidate):
                html_url = candidate

        # If primary_doc failed or was not set, scan index page
        if not html_url:
            resp = requests.get(index_url, headers=HEADERS)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")

                for a in soup.find_all("a"):
                    href = a.get("href", "").lower()
                    if href.endswith(".htm") and form_type.lower() in href:
                        candidate = f"https://www.sec.gov{href}"
                        if validate_url(candidate):
                            html_url = candidate
                            break

        # Look for .xlsx financials
        resp = requests.get(index_url, headers=HEADERS)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a"):
                href = a.get("href", "").lower()
                if href.endswith(".xlsx") and "financial" in href:
                    candidate = f"https://www.sec.gov{href}"
                    if validate_url(candidate):
                        excel_url = candidate
                        break
    except:
        pass

    return {
        "Index Page": index_url,
        "HTML Report": html_url,
        "Excel Report": excel_url
    }

def get_latest_filing(cik, form_type):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            return None, None

        data = response.json()
        filings = data.get("filings", {}).get("recent", {})
        form_types = filings.get("form", [])
        accession_numbers = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])
        filing_dates = filings.get("filingDate", [])

        cutoff = datetime.now() - timedelta(days=2*365)

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
    except:
        pass
    return None, None

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    cik, matched_name = resolve_cik(company_name)
    if not cik:
        return {"error": f"Unable to resolve CIK for {company_name}"}

    q_accession, q_primary_doc = get_latest_filing(cik, "10-Q")
    k_accession, k_primary_doc = get_latest_filing(cik, "10-K")

    q_urls = get_actual_filing_urls(cik, q_accession, q_primary_doc, "10-Q") if q_accession else {}
    k_urls = get_actual_filing_urls(cik, k_accession, k_primary_doc, "10-K") if k_accession else {}

    push_new_aliases_to_github()

    return {
        "Matched Company Name": matched_name,
        "CIK": cik,
        "10-Q Filing": q_urls.get("HTML Report") or "No recent 10-Q found",
        "10-K Filing": k_urls.get("HTML Report") or k_urls.get("Excel Report") or "No recent 10-K found"
    }
