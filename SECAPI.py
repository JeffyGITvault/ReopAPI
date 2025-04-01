from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-Q and financial report for specific public companies.",
    version="v2.0.5"  # Base API 2
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

COMPANIES = {
    "Central Garden & Pet": "0000887733",
    "Restoration Hardware (RH)": "0001528849",
    "Ball Corporation": "0000009389",
    "DISH Network Corporation": "0001001082",
    "Frontier Airlines": "0001670076",
    "Community Health Systems": "0001108109",
    "Expeditors International": "0000746515",
    "iHeartMedia, Inc.": "0001400891",
    "Caesars Entertainment": "0000858339",
    "Boyd Gaming Corporation": "0001309848",
    "Penn Entertainment, Inc.": "0000921738",
    "Bally's Corporation": "0001747079",
    "Tri-State Energy": "0001637880",
}

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"message": "SEC API is live!"}

def get_actual_filing_urls(cik, accession, primary_doc):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"
    full_10q_url = base_url + primary_doc

    response = requests.get(index_url, headers=HEADERS)
    if response.status_code != 200:
        return {
            "10-Q Index Page": index_url,
            "10-Q Report": full_10q_url,
            "Financial Report (Excel)": None
        }

    soup = BeautifulSoup(response.text, "html.parser")
    financial_report = None

    for link in soup.find_all("a"):
        href = link.get("href")
        if not href:
            continue
        if "financial_report.xlsx" in href.lower():
            financial_report = f"https://www.sec.gov{href}"
            break

    return {
        "10-Q Index Page": index_url,
        "10-Q Report": full_10q_url,
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

    for i, form in enumerate(filings["form"]):
        if form == "10-Q":
            accession = filings["accessionNumber"][i].replace("-", "")
            primary_doc = filings["primaryDocument"][i]
            return get_actual_filing_urls(cik, accession, primary_doc)

    return {"error": "No 10-Q filing found"}

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    company_name = company_name.lower().strip()
    cik = next((v for k, v in COMPANIES.items() if company_name in k.lower()), None)
    if not cik:
        return {"error": "Company not found in database"}
    return get_filings(cik)
