from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
from cik_resolver import resolve_cik, push_new_aliases_to_github

app = FastAPI(
    title="Get SEC Filings Data",
    description="Fetches the latest 10-Q filings for a company. Uses CIK resolution, alias mapping, and GitHub-based alias updates. Returns the most recent 10-Q HTML reports.",
    version="v4.3.0"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

# === Utilities ===
def validate_url(url):
    try:
        resp = requests.head(url, headers=HEADERS)
        return resp.status_code == 200
    except:
        return False

def get_actual_filing_url(cik, accession, primary_doc):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"
    html_url = None

    try:
        # Prefer the primary_doc if it's valid
        if primary_doc and primary_doc.endswith(".htm"):
            html_url = base_url + primary_doc

        # Validate or fallback to best .htm from index
        resp = requests.get(index_url, headers=HEADERS)
        if resp.status_code == 200 and not validate_url(html_url):
            soup = BeautifulSoup(resp.text, "html.parser")
            candidates = []
            for a in soup.find_all("a"):
                href = a.get("href", "").lower()
                if href.endswith(".htm"):
                    score = 0
                    if "10q" in href: score += 3
                    if "form" in href or "main" in href: score += 2
                    if "index" in href or "cover" in href or "summary" in href: score -= 1
                    candidates.append((score, href))
            candidates.sort(reverse=True)
            for _, href in candidates:
                candidate_url = f"https://www.sec.gov{href}"
                if validate_url(candidate_url):
                    html_url = candidate_url
                    break
    except Exception as e:
        print(f"[ERROR] Exception while fetching filing URL: {e}")

    return html_url or "Unavailable"

# === Endpoints ===
@app.get("/get_quarterlies/{company_name}")
def get_quarterly_filings(company_name: str, count: int = 4):
    cik, matched_name = resolve_cik(company_name)
    if not cik:
        return {"error": f"Unable to resolve CIK for {company_name}"}

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            return {"error": f"Failed to fetch filings for {matched_name}"}

        data = response.json()
        filings = data.get("filings", {}).get("recent", {})
        form_types = filings.get("form", [])
        accession_numbers = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])
        filing_dates = filings.get("filingDate", [])

        quarterly_reports = []
        for i, form in enumerate(form_types):
            if form != "10-Q":
                continue
            accession = accession_numbers[i].replace("-", "")
            primary_doc = primary_docs[i]
            filing_date = filing_dates[i]
            html_url = get_actual_filing_url(cik, accession, primary_doc)
            quarterly_reports.append({
                "Filing Date": filing_date,
                "HTML Report": html_url
            })
            if len(quarterly_reports) == count:
                break

        push_new_aliases_to_github()

        return {
            "Matched Company Name": matched_name,
            "CIK": cik,
            "10-Q Filings": quarterly_reports
        }

    except Exception as e:
        return {"error": f"Exception while fetching data: {e}"}
