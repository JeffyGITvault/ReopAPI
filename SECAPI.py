from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime, timedelta

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-Q and financial report for any public company by dynamically resolving the CIK.",
    version="v3.0.0"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

# Load ticker and name to CIK mapping from SEC JSON file
def load_ticker_mapping():
    try:
        response = requests.get("https://www.sec.gov/files/company_tickers.json", headers=HEADERS)
        data = response.json()
        return {
            entry["title"].lower(): str(entry["cik_str"]).zfill(10)
            for entry in data.values()
        }
    except Exception as e:
        print(f"Failed to fetch ticker mapping: {e}")
        return {}

COMPANY_MAP = load_ticker_mapping()

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"message": "SEC API is live!"}

def resolve_cik_from_sec(company_name: str):
    normalized_name = company_name.lower().strip()
    if normalized_name in COMPANY_MAP:
        return COMPANY_MAP[normalized_name]

    query = re.sub(r'(,?\s+(Inc|Corp|Corporation|LLC|Ltd))\.?$', '', company_name, flags=re.IGNORECASE)
    query = query.replace(" ", "+")
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={query}&match=contains&action=getcompany"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    cik_tag = soup.find("a", href=True, string=lambda x: x and x.isdigit())
    if cik_tag:
        cik = cik_tag.text.strip().zfill(10)
        print(f"Resolved CIK for '{company_name}' as '{cik}'")  # Debug logging
        return cik
    return None

def get_actual_filing_urls(cik, accession, primary_doc):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"
    primary_doc_url = base_url + primary_doc

    ten_q_report = primary_doc_url if primary_doc.lower().endswith(".htm") else None
    financial_report = None

    response = requests.get(index_url, headers=HEADERS)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        htm_candidates = []
        for link in soup.find_all("a"):
            href = link.get("href")
            if not href:
                continue
            href_lower = href.lower()
            if href_lower.endswith(".htm") and "summary" not in href_lower and "index" not in href_lower:
                if "10q" in href_lower or "10k" in href_lower:
                    htm_candidates.insert(0, href)  # prioritize relevant documents
                else:
                    htm_candidates.append(href)
            elif "financial_report.xlsx" in href_lower:
                financial_report = f"https://www.sec.gov{href}"

        if not ten_q_report and htm_candidates:
            ten_q_report = f"https://www.sec.gov{htm_candidates[0]}"

    return {
        "Latest Filing Index URL": index_url,
        "Full Filing Report": ten_q_report,
        "Financial Report (Excel)": financial_report
    }

def get_filings(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        return {"error": f"Failed to retrieve filings for CIK {cik}"}

    data = response.json()
    filings = data.get("filings", {}).get("recent", {})

    if not filings.get("form"):
        return {"error": "No recent filings found"}

    today = datetime.today()
    three_years_ago = today - timedelta(days=3*365)

    for i, form in enumerate(filings["form"]):
        if form in ["10-Q", "10-K"]:
            filing_date_str = filings["filingDate"][i]
            filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d")
            if filing_date >= three_years_ago:
                accession = filings["accessionNumber"][i].replace("-", "")
                primary_doc = filings["primaryDocument"][i]
                return get_actual_filing_urls(cik, accession, primary_doc)

    return {"error": "No recent 10-K or 10-Q filings within the last 3 years"}

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    company_name = company_name.strip()
    cik = resolve_cik_from_sec(company_name)
    if not cik:
        return {"error": f"Company '{company_name}' not found in SEC database"}
    return get_filings(cik)
