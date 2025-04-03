from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-Q or 10-K SEC filings and Excel financial reports for supported public companies. Uses dynamic CIK resolution with fallback logic and alias matching.",
    version="v3.2.1"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

ALIAS_MAP = {
    "rh": "Restoration Hardware",
    "goog": "Alphabet Inc.",
    "google": "Alphabet Inc.",
    "meta": "Meta Platforms, Inc.",
    "fb": "Meta Platforms, Inc.",
    "cent": "Central Garden & Pet Company",
    "ball corp": "Ball Corporation",
    "ball": "Ball Corporation"
}

def resolve_cik(company_name: str):
    original_name = company_name
    name_key = company_name.lower().strip()
    resolved_name = ALIAS_MAP.get(name_key, company_name)

    cleaned = re.sub(r'(,?\s+(Inc|Corp|Corporation|LLC|Ltd)\.?$)', '', resolved_name, flags=re.IGNORECASE)
    query = cleaned.replace(" ", "+")
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={query}&match=contains&action=getcompany"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return None, resolved_name

    soup = BeautifulSoup(resp.text, "html.parser")
    cik_tag = soup.find("a", href=True, string=lambda x: x and x.isdigit())
    if cik_tag:
        return cik_tag.text.strip().zfill(10), resolved_name
    return None, resolved_name

def get_actual_filing_urls(cik, accession, primary_doc):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"
    report_url = base_url + primary_doc if primary_doc.endswith(".htm") else None
    excel_url = None

    resp = requests.get(index_url, headers=HEADERS)
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a"):
            href = a.get("href", "").lower()
            if not href:
                continue
            full_url = f"https://www.sec.gov{href}"
            if not report_url and href.endswith(".htm") and ("10q" in href or "10-k" in href):
                report_url = full_url
            if href.endswith("financial_report.xlsx"):
                excel_url = full_url

    return {
        "10-K/10-Q Index Page": index_url if "index.html" in index_url else None,
        "Full HTML Filing Report": report_url if report_url and report_url.endswith(".htm") else None,
        "Financial Report (Excel)": excel_url if excel_url and excel_url.endswith(".xlsx") else None
    }

def get_filings(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        return None

    data = response.json()
    filings = data.get("filings", {}).get("recent", {})
    form_types = filings.get("form", [])
    accession_numbers = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [])
    filing_dates = filings.get("filingDate", [])

    cutoff = datetime.now() - timedelta(days=3*365)

    for i, form in enumerate(form_types):
        try:
            filing_date = datetime.strptime(filing_dates[i], "%Y-%m-%d")
            if filing_date < cutoff:
                continue

            if form in ("10-Q", "10-K"):
                accession = accession_numbers[i].replace("-", "")
                return accession, primary_docs[i]
        except Exception:
            continue
    return None, None

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    cik, matched_name = resolve_cik(company_name)
    if not cik:
        return {"error": f"Unable to resolve CIK for {company_name}"}

    accession, primary_doc = get_filings(cik)
    if not accession:
        return {"error": f"No 10-Q or 10-K filings found for {matched_name} in the last 3 years"}

    urls = get_actual_filing_urls(cik, accession, primary_doc)
    return {
        **urls,
        "CIK": cik,
        "Matched Company Name": matched_name
    }
