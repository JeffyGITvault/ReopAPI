from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-Q and financial report for specific public companies.",
    version="v2.0.3"
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
    "Boyd Gaming Corporation": "0000003545",
    "Penn Entertainment, Inc.": "0000921738",
    "Bally's Corporation": "0001747079",
    "Harrah's Entertainment": "0000049939",
    "Tri-State Energy": "0001637880"
}

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"message": "SEC API is live!"}

def get_actual_filing_urls(index_url):
    """
    Parses the SEC index.html page and extracts direct links to:
    - The Financial_Report.xlsx file (if available)
    """
    response = requests.get(index_url, headers=HEADERS)
    if response.status_code != 200:
        return {}

    soup = BeautifulSoup(response.text, "html.parser")
    financial_report_url = None

    for link in soup.find_all("a"):
        href = link.get("href")
        if href and "Financial_Report.xlsx" in href:
            financial_report_url = f"https://www.sec.gov{href}"

    return {
        "Financial Report (Excel)": financial_report_url or None
    }

def get_filings(cik):
    """
    Fetches the latest 10-Q filing for a given CIK and builds valid clickable URLs.
    """
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
            accession = filings["accessionNumber"][i]
            primary_doc = filings["primaryDocument"][i]
            folder = accession.replace("-", "")
            ten_q_index_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{folder}/index.html"
            ten_q_report_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{folder}/{primary_doc}"

            result = {
                "10-Q Index Page": ten_q_index_url,
                "10-Q Report": ten_q_report_url
            }

            result.update(get_actual_filing_urls(ten_q_index_url))
            return result

    return {"error": "No 10-Q filing found"}

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    company_name = company_name.lower().strip()
    cik = next((v for k, v in COMPANIES.items() if company_name in k.lower()), None)
    if not cik:
        return {"error": "Company not found in database"}
    return get_filings(cik)
