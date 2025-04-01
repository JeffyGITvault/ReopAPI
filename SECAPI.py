from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the most recent 10-Q or 10-K report and financials (if available) for any public company.",
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
    return cik_tag.text.strip().zfill(10) if cik_tag else None

def get_actual_filing_urls(cik, accession, primary_doc):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"
    html_report_url = base_url + primary_doc if primary_doc.lower().endswith(".htm") else None
    excel_url = None

    response = requests.get(index_url, headers=HEADERS)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a"):
            href = link.get("href")
            if not href:
                continue
            if "financial_report.xlsx" in href.lower():
                excel_url = f"https://www.sec.gov{href}"
                break

    return {
        "10-K/10-Q Index Page": f"[10-K/10-Q Index Page]({index_url})" if index_url else None,
        "Full HTML Report": f"[Full HTML Report]({html_report_url})" if html_report_url else None,
        "Excel Financials": f"[Excel Financials]({excel_url})" if excel_url else None
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

    filing_types = ["10-Q", "10-K"]
    candidates = [
        (i, filings["accessionNumber"][i].replace("-", ""), filings["primaryDocument"][i], filings["filingDate"][i])
        for i, form in enumerate(filings["form"])
        if form in filing_types
    ]

    if not candidates:
        return {"error": "No 10-Q or 10-K filing found"}

    candidates.sort(key=lambda x: x[3], reverse=True)
    _, accession, primary_doc, _ = candidates[0]
    return get_actual_filing_urls(cik, accession, primary_doc)

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    company_name = company_name.strip()
    cik = resolve_cik_from_sec(company_name)
    if not cik:
        return {"error": f"Company '{company_name}' not found in SEC database"}
    return get_filings(cik)
