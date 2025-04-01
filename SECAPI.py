from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-Q or fallback 10-K, and Excel financial report for any public company by dynamically resolving the CIK.",
    version="v3.1.0"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"message": "SEC API is live!"}

def resolve_cik_from_sec(company_name: str):
    cleaned = re.sub(r'(,?\s+(Inc|Corp|Corporation|LLC|Ltd))?\.?$', '', company_name, flags=re.IGNORECASE)
    query = cleaned.replace(" ", "+")
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

    ten_x_report = primary_doc_url if primary_doc.lower().endswith(".htm") else None
    financial_report = None

    response = requests.get(index_url, headers=HEADERS)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a"):
            href = link.get("href")
            if not href:
                continue
            full_url = f"https://www.sec.gov{href}"
            if not ten_x_report and href.lower().endswith(".htm") and ("10-q" in href.lower() or "10-k" in href.lower()):
                ten_x_report = full_url
            elif "financial_report.xlsx" in href.lower():
                financial_report = full_url

    return {
        "10-K/10-Q Index Page": f"[📄 10-K / 10-Q Index Page]({index_url})" if index_url else None,
        "Full Filing Report": f"[📘 Full HTML Filing Report]({ten_x_report})" if ten_x_report else None,
        "Financial Report (Excel)": f"[📊 Download Excel Financials]({financial_report})" if financial_report else None
    }

def parse_date_safe(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return datetime.min

def get_latest_filing(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        return {"error": f"Failed to retrieve filings for CIK {cik}"}

    data = response.json()
    filings = data.get("filings", {}).get("recent", {})

    if not filings.get("form"):
        return {"error": "No recent filings found"}

    preferred_forms = ["10-Q", "10-K"]
    for form_type in preferred_forms:
        candidates = [
            (i, filings["accessionNumber"][i].replace("-", ""), filings["primaryDocument"][i], filings["filingDate"][i])
            for i, form in enumerate(filings["form"])
            if form == form_type
        ]
        three_years_ago = datetime.today() - timedelta(days=3*365)
        candidates = [c for c in candidates if parse_date_safe(c[3]) >= three_years_ago]
        if candidates:
            candidates.sort(key=lambda x: parse_date_safe(x[3]), reverse=True)
            i, accession, primary_doc, _ = candidates[0]
            return get_actual_filing_urls(cik, accession, primary_doc)

    return {"error": "No 10-Q or 10-K filing found"}

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    company_name = company_name.strip()
    cik = resolve_cik_from_sec(company_name)
    if not cik:
        return {"error": f"Company '{company_name}' not found in SEC database"}
    return get_latest_filing(cik)
