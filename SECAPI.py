from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-K and 10-Q SEC filings for a company, including direct links to the financial report and full filing document.",
    version="v2.0.0"
)

HEADERS = {"User-Agent": "Your Name (your@email.com)"}

COMPANIES = {
    "Central Garden & Pet": "0000887733",
    "Restoration Hardware (RH)": "0001528849",
    "Ball Corporation": "0000009389",
    "DISH Network Corporation": "0001001082",
    "Frontier Airlines": "0001034645",
    "Community Health Systems": "0001108109",
    "Expeditors International": "0000746515",
    "iHeartMedia, Inc.": "0001400891",
    "Caesars Entertainment": "0000858339",
    "Boyd Gaming Corporation": "0000003545",
    "Penn Entertainment, Inc.": "0000921738",
    "Bally's Corporation": "0001747079",
    "Harrah's Entertainment": "0000049939",
    "Tri-State Energy": "0001637880",
}

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"message": "SEC API is live!"}

def get_actual_filing_urls(index_url):
    """
    Parses the SEC index.html page and extracts direct links to:
    1. The full 10-K and 10-Q report (.htm)
    2. The Financial_Report.xlsx file (if available)
    """
    response = requests.get(index_url, headers=HEADERS)
    if response.status_code != 200:
        return {"error": "Failed to fetch SEC index page"}

    soup = BeautifulSoup(response.text, "html.parser")

    ten_k_htm_url = None
    ten_q_htm_url = None
    financial_report_url = None

    for link in soup.find_all("a"):
        href = link.get("href")

        if href:
            # Find 10-K HTML Report
            if "10-k" in href.lower() and href.endswith(".htm"):
                ten_k_htm_url = f"https://www.sec.gov{href}"

            # Find 10-Q HTML Report
            if "10-q" in href.lower() and href.endswith(".htm"):
                ten_q_htm_url = f"https://www.sec.gov{href}"

            # Find Financial Report Excel File
            if "Financial_Report.xlsx" in href:
                financial_report_url = f"https://www.sec.gov{href}"

    return {
        "10-K Report": ten_k_htm_url if ten_k_htm_url else "Not Found",
        "10-Q Report": ten_q_htm_url if ten_q_htm_url else "Not Found",
        "Financial Report (Excel)": financial_report_url if financial_report_url else "Not Found"
    }

def get_filings(cik):
    """Fetch the latest 10-K and 10-Q filings for a given CIK"""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        return {"error": f"Failed to retrieve filings for CIK {cik}"}

    data = response.json()
    filings = data["filings"]["recent"]

    if not filings["form"]:
        return {"error": "No recent filings found"}

    ten_k_index_url = None
    ten_q_index_url = None

    for i, form in enumerate(filings["form"]):
        if form == "10-K" and not ten_k_index_url:
            ten_k_index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{filings['accessionNumber'][i].replace('-', '')}/index.html"
        elif form == "10-Q" and not ten_q_index_url:
            ten_q_index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{filings['accessionNumber'][i].replace('-', '')}/index.html"

        if ten_k_index_url and ten_q_index_url:
            break

    filing_data = {
        "10-K Index Page": ten_k_index_url if ten_k_index_url else "Not Found",
        "10-Q Index Page": ten_q_index_url if ten_q_index_url else "Not Found",
    }

    # Fetch actual file links if available
    if ten_k_index_url:
        filing_data.update(get_actual_filing_urls(ten_k_index_url))

    if ten_q_index_url:
        filing_data.update(get_actual_filing_urls(ten_q_index_url))

    return filing_data

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    """API endpoint to fetch 10-K and 10-Q filings for a company, including direct document links."""
    company_name = company_name.lower().strip()
    cik = None

    for name, cik_value in COMPANIES.items():
        if company_name in name.lower():
            cik = cik_value
            break

    if not cik:
        return {"error": "Company not found in our database"}

    return get_filings(cik)
