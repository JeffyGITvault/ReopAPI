from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import base64
import json
import os

from cik_resolver import resolve_cik, NEW_ALIASES

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-Q for viewing and 10-K for Excel download. Uses dynamic CIK resolution, alias mapping, and fallback logic.",
    version="v4.2.4"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ALIAS_GITHUB_JSON = "https://raw.githubusercontent.com/JeffyGITvault/ReopAPI/main/alias_map.json"
ALIAS_PUSH_URL = "https://api.github.com/repos/JeffyGITvault/ReopAPI/contents/alias_map.json"

# === Utility ===
def validate_url(url):
    try:
        resp = requests.head(url, headers=HEADERS)
        return resp.status_code == 200
    except:
        return False

def push_new_aliases_to_github():
    if not NEW_ALIASES or not GITHUB_TOKEN:
        return

    try:
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }

        # Step 1: Fetch current alias_map.json
        get_resp = requests.get(ALIAS_PUSH_URL, headers=headers)
        if get_resp.status_code != 200:
            print(f"❌ Failed to fetch alias_map.json metadata: {get_resp.status_code}")
            return

        sha = get_resp.json().get("sha")
        current_content = requests.get(ALIAS_GITHUB_JSON, headers=HEADERS).json()

        updated_content = {**current_content, **NEW_ALIASES}

        if updated_content == current_content:
            print("⚠️ No new changes to commit — skipping push.")
            return

        encoded = base64.b64encode(json.dumps(updated_content, indent=4).encode("utf-8")).decode("utf-8")

        commit_payload = {
            "message": "🔁 Update alias_map.json with learned aliases",
            "content": encoded,
            "sha": sha
        }

        put_resp = requests.put(ALIAS_PUSH_URL, headers=headers, json=commit_payload)
        if put_resp.status_code in [200, 201]:
            print("✅ GitHub alias_map.json updated successfully")
        else:
            print(f"❌ GitHub update failed: {put_resp.status_code} → {put_resp.text}")

    except Exception as e:
        print(f"❌ Exception during GitHub alias push: {e}")


def get_actual_filing_urls(cik, accession, primary_doc):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"
    report_url = base_url + primary_doc if primary_doc and primary_doc.endswith(".htm") else None
    excel_url = None

    resp = requests.get(index_url, headers=HEADERS)
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        found_excel_files = []
        for a in soup.find_all("a"):
            href = a.get("href", "").lower()
            if not href:
                continue
            full_url = f"https://www.sec.gov{href}"
            if not report_url and href.endswith(".htm") and ("10q" in href or "10-k" in href):
                report_url = full_url
            if href.endswith(".xlsx") and "financial" in href:
                found_excel_files.append(full_url)

        for url in found_excel_files:
            if validate_url(url):
                excel_url = url
                break

    return {
        "10-K/10-Q Index Page": index_url,
        "Full HTML Filing Report": report_url or "❌ Not available",
        "Financial Report (Excel)": excel_url or "❌ Not available"
    }

def get_latest_filing(cik, form_type):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        return None, None

    data = response.json()
    filings = data.get("filings", {}).get("recent", {})
    form_types = filings.get("form", [])
    accession_numbers = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [])
    filing_dates = filings.get("filingDate", [])

    cutoff = datetime.now() - timedelta(days=5*365)

    for i, form in enumerate(form_types):
        try:
            filing_date = datetime.strptime(filing_dates[i], "%Y-%m-%d")
            if filing_date < cutoff:
                continue
            if form == form_type:
                accession = accession_numbers[i].replace("-", "")
                return accession, primary_docs[i]
        except:
            continue
    return None, None

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    input_key = company_name.lower().strip()
    cik, matched_name = resolve_cik(input_key)
    if not cik:
        return {"error": f"Unable to resolve CIK for {company_name}"}

    q_accession, q_primary_doc = get_latest_filing(cik, "10-Q")
    k_accession, k_primary_doc = get_latest_filing(cik, "10-K")

    q_urls = get_actual_filing_urls(cik, q_accession, q_primary_doc) if q_accession else {}
    k_urls = get_actual_filing_urls(cik, k_accession, k_primary_doc) if k_accession else {}

    if NEW_ALIASES:
        print(f"🔄 Committing {len(NEW_ALIASES)} learned aliases to GitHub...")
        push_new_aliases_to_github()
        NEW_ALIASES.clear()

    return {
        "Matched Company Name": matched_name,
        "CIK": cik,
        "10-Q Filing": {
            "10-K/10-Q Index Page": q_urls.get("10-K/10-Q Index Page", "❌ Not available"),
            "Full HTML Filing Report": q_urls.get("Full HTML Filing Report", "❌ Not available"),
            "Financial Report (Excel)": q_urls.get("Financial Report (Excel)", "❌ Not available")
        } if q_urls else "No recent 10-Q found",
        "10-K Excel": k_urls.get("Financial Report (Excel)", "❌ Not available")
    }

@app.get("/docs/openapi", include_in_schema=False)
def get_openapi_json():
    url = "https://raw.githubusercontent.com/JeffyGITvault/ReopAPI/main/openapi.json"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    return {"error": "Unable to fetch OpenAPI JSON from GitHub"}
