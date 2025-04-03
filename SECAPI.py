from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-Q or 10-K SEC filings and Excel financial reports for supported public companies.",
    version="v3.2.0"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
SEC_YEARS_LIMIT = 3  # Filter filings within the last 3 years

ALIAS_MAP = {
    "rh": "Restoration Hardware",
    "hd": "Home Depot",
    "goog": "Alphabet Inc.",
    "googl": "Alphabet Inc.",
    "google": "Alphabet Inc.",
    "meta": "Meta Platforms Inc.",
    "facebook": "Meta Platforms Inc.",
    "cent": "Central Garden & Pet Company",
    "central garden": "Central Garden & Pet Company",
    "dish": "DISH Network Corporation"
}

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"message": "SEC API is live!"}

def resolve_cik(company_name: str):
    alias_key = company_name.strip().lower()
    resolved_name = ALIAS_MAP.get(alias_key, company_name)
    query = resolved_name.replace(" ", "+")
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
    html_report_url = base_url + primary_doc if primary_doc.lower().endswith(".htm") else None
    financial_excel_url = None

    resp = requests.get(index_url, headers=HEADERS)
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("a"):
            href = link.get("href", "").lower()
            if not href:
                continue
            if not html_report_url and href.endswith(".htm") and ("10q" in href or "10-k" in href):
                html_report_url = f"https://www.sec.gov{href}"
            elif "financial_report.xlsx" in href:
                financial_excel_url = f"https://www.sec.gov{href}"

    return index_url, html_report_url, financial_excel_url

def get_recent_filing(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return None

    data = resp.json()
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    documents = recent.get("primaryDocument", [])
    dates = recent.get("filingDate", [])

    for i, form in enumerate(forms):
        try:
            fdate = datetime.strptime(dates[i], "%Y-%m-%d")
            if fdate < datetime.now() - timedelta(days=365 * SEC_YEARS_LIMIT):
                continue
            if form in ["10-Q", "10-K"]:
                return accessions[i].replace("-", ""), documents[i], form
        except:
            continue

    return None

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    cik, normalized = resolve_cik(company_name)
    if not cik:
        return {"error": f"No CIK found for '{company_name}'"}

    filing = get_recent_filing(cik)
    if not filing:
        return {"error": f"No 10-K or 10-Q filings found for '{normalized}' in last 3 years."}

    accession, primary_doc, form_type = filing
    index, html_url, excel_url = get_actual_filing_urls(cik, accession, primary_doc)

    return {
        "10-K/10-Q Index Page": index,
        "Full Filing Report": html_url,
        "Financial Report (Excel)": excel_url,
        "CIK": cik,
        "Matched Company Name": normalized
    }
