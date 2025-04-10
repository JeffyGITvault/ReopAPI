from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import base64
import json
import os
from difflib import SequenceMatcher

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

def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def push_new_aliases_to_github():
    if not NEW_ALIASES or not GITHUB_TOKEN:
        print("⚠️ No aliases or token present, skipping push.")
        return

    try:
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }

        get_resp = requests.get(ALIAS_PUSH_URL, headers=headers)
        if get_resp.status_code != 200:
            print(f"❌ Failed to fetch alias_map.json metadata: {get_resp.status_code}")
            return

        sha = get_resp.json().get("sha")
        content_resp = requests.get(ALIAS_GITHUB_JSON, headers=HEADERS)
        if content_resp.status_code != 200:
            print(f"❌ Failed to fetch current alias_map.json: {content_resp.status_code}")
            return

        current_content = content_resp.json()
        delta = {k: v for k, v in NEW_ALIASES.items() if current_content.get(k) != v}
        if not delta:
            print("⚠️ No new aliases to update — skipping push.")
            return

        updated_content = {**current_content, **delta}
        encoded = base64.b64encode(json.dumps(updated_content, indent=4).encode("utf-8")).decode("utf-8")

        commit_payload = {
            "message": "🔁 Update alias_map.json with learned aliases",
            "content": encoded,
            "sha": sha
        }

        put_resp = requests.put(ALIAS_PUSH_URL, headers=headers, json=commit_payload)
        if put_resp.status_code in [200, 201]:
            print(f"✅ GitHub alias_map.json updated successfully with {len(delta)} aliases")
            NEW_ALIASES.clear()
        else:
            print(f"❌ GitHub update failed: {put_resp.status_code} → {put_resp.text}")

    except Exception as e:
        print(f"❌ Exception during GitHub alias push: {e}")

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

    if cik:
        if input_key != matched_name.lower().strip():
            if similar(input_key, matched_name) > 0.8:
                NEW_ALIASES[input_key] = matched_name
            else:
                print(f"⚠️ Match for '{company_name}' → '{matched_name}' failed similarity check")
        else:
            NEW_ALIASES[input_key] = matched_name

    if not cik:
        return {"error": f"Unable to resolve CIK for {company_name}"}

    q_accession, q_primary_doc = get_latest_filing(cik, "10-Q")
    k_accession, k_primary_doc = get_latest_filing(cik, "10-K")

    q_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{q_accession}/{q_primary_doc}" if q_accession and q_primary_doc else None
    k_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{k_accession}/{k_primary_doc}" if k_accession and k_primary_doc else None

    formatted_q = f"[📘 View Filing]({q_url})" if q_url else "❌ Not available"
    formatted_k = f"[📊 Download Excel]({k_url})" if k_url and k_url.endswith(".xlsx") else "❌ Not available"

    if NEW_ALIASES:
        print(f"🔄 Committing {len(NEW_ALIASES)} learned aliases to GitHub...")
        push_new_aliases_to_github()

    return {
        "Matched Company Name": matched_name,
        "CIK": cik,
        "10-Q Filing": formatted_q,
        "10-K Excel": formatted_k
    }

@app.get("/docs/openapi", include_in_schema=False)
def get_openapi_json():
    url = "https://raw.githubusercontent.com/JeffyGITvault/ReopAPI/main/openapi.json"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    return {"error": "Unable to fetch OpenAPI JSON from GitHub"}
