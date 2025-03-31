from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-Q and financial report for specific public companies.",
    version="v2.0.4"
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
    "Tri-State Energy": "0001637880",
}

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"message": "SEC API is live!"}

def get_actual_filing_urls(index_url, fallback_html_url):
    response = requests.get(index_url, headers=HEADERS)
    if response.status_code != 200:
        return {}

    soup = BeautifulSoup(response.text, "html.parser")
    ten_q_htm_url = None
    financial_report_url = None

    for link in soup.find_all("a"):
        href = link.get("href")
        if href:
            if href.lower().endswith(".htm") and ("10q" in href.lower() or "10-q" in href.lower()):
                ten_q_htm_url = f"https://www.sec.gov{href}"
            if "financial_report.xlsx" in href.lower():
                financial_report_url = f"https://www.sec.gov{href}"

    # Fallback to primary document URL if no 10-Q HTML link is found
    if not ten_q_htm_url:
        ten_q_htm_url = fallback_html_url

    return {
        "10-Q Report": ten_q_htm_url,
        "Financial Report (Excel)": financial_report_url or None
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
            accession = filings["accessionNumber"][i]
            primary_doc = filings["primaryDocument"][i]
            folder = accession.replace("-", "")
            ten_q_index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/index.html"
            ten_q_report_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{primary_doc}"

            result = {
                "10-Q Index Page": ten_q_index_url,
                "10-Q Report": ten_q_report_url  # Default, might be overwritten if better one found
            }

            # Attempt to enhance 10-Q Report link
            result.update(get_actual_filing_urls(ten_q_index_url, ten_q_report_url))
            return result

    return {"error": "No 10-Q filing found"}

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    company_name = company_name.lower().strip()
    cik = next((v for k, v in COMPANIES.items() if company_name in k.lower()), None)
    if not cik:
        return {"error": "Company not found in database"}
    return get_filings(cik)
