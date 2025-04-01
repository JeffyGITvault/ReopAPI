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
        return cik_tag.text.strip().zfill(10)
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
        for link in soup.find_all("a"):
            href = link.get("href")
            if not href:
                continue
            full_url = f"https://www.sec.gov{href}"
            if not ten_q_report and href.lower().endswith(".htm") and "10-q" in href.lower():
                ten_q_report = full_url
            elif "financial_report.xlsx" in href.lower():
                financial_report = full_url

    return {
        "10-K/10-Q Index Page": f"[10-K / 10-Q Index Page (SEC)]({index_url})" if index_url else None,
        "Full Filing Report": f"[Full HTML Filing Report]({ten_q_report})" if ten_q_report else None,
        "Financial Report (Excel)": f"[Download Excel Financials]({financial_report})" if financial_report else None
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

    filings_list = []
    for i, form in enumerate(filings["form"]):
        if form in ["10-Q", "10-K"]:
            filing_date_str = filings["filingDate"][i]
            try:
                filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d")
            except ValueError:
                continue

            if filing_date >= three_years_ago:
                filings_list.append({
                    "form": form,
                    "date": filing_date,
                    "accession": filings["accessionNumber"][i].replace("-", ""),
                    "primary_doc": filings["primaryDocument"][i]
                })

    if not filings_list:
        return {"error": "No recent 10-K or 10-Q filings within the last 3 years"}

    latest_filing = sorted(filings_list, key=lambda x: x["date"], reverse=True)[0]
    return get_actual_filing_urls(cik, latest_filing["accession"], latest_filing["primary_doc"])

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    company_name = company_name.strip()
    cik = resolve_cik_from_sec(company_name)
    if not cik:
        return {"error": f"Company '{company_name}' not found in SEC database"}
    return get_filings(cik)

