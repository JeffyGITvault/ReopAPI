from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime, timedelta
from cik_resolver import resolve_cik, push_new_aliases_to_github

app = FastAPI(
    title="Get SEC Filings Data",
    description="Fetches the latest 10-Q and 10-K filings, with logging for better debugging.",
    version="v4.2.6-debug"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

def validate_url(url):
    try:
        resp = requests.head(url, headers=HEADERS)
        print(f"🔎 Validating URL: {url} → {resp.status_code}")
        return resp.status_code == 200
    except Exception as e:
        print(f"❌ URL validation error: {e}")
        return False

def get_actual_filing_urls(cik, accession, primary_doc, form_type):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"
    html_url = None
    excel_url = None

    print(f"🔗 Accessing index page: {index_url}")

    try:
        if form_type == "10-Q" and primary_doc and primary_doc.endswith(".htm"):
            html_url = base_url + primary_doc
            print(f"✅ Primary doc HTML set from SEC JSON: {html_url}")

        resp = requests.get(index_url, headers=HEADERS)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")

            if not html_url:
                for a in soup.find_all("a"):
                    href = a.get("href", "").lower()
                    if href.endswith(".htm") and form_type.lower() in href:
                        candidate = f"https://www.sec.gov{href}"
                        if validate_url(candidate):
                            html_url = candidate
                            print(f"🔁 HTML fallback match: {html_url}")
                            break

            for a in soup.find_all("a"):
                href = a.get("href", "").lower()
                if href.endswith(".xlsx") and "financial" in href:
                    candidate = f"https://www.sec.gov{href}"
                    if validate_url(candidate):
                        excel_url = candidate
                        print(f"📊 Excel match found: {excel_url}")
                        break
    except Exception as e:
        print(f"❌ Error parsing index page: {e}")

    return {
        "Index Page": index_url,
        "HTML Report": html_url,
        "Excel Report": excel_url
    }

def get_latest_filing(cik, form_type):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    print(f"📥 Fetching JSON: {url}")
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            print(f"❌ SEC JSON fetch failed: {response.status_code}")
            return None, None

        data = response.json()
        filings = data.get("filings", {}).get("recent", {})
        form_types = filings.get("form", [])
        accession_numbers = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])
        filing_dates = filings.get("filingDate", [])

        cutoff = datetime.now() - timedelta(days=2*365)

        for i, form in enumerate(form_types):
            try:
                filing_date = datetime.strptime(filing_dates[i], "%Y-%m-%d")
                if filing_date < cutoff:
                    continue
                if form == form_type:
                    accession = accession_numbers[i].replace("-", "")
                    print(f"📄 Found {form_type}: accession={accession}, doc={primary_docs[i]}")
                    return accession, primary_docs[i]
            except Exception as e:
                print(f"⚠️ Error reading filing {i}: {e}")
                continue
    except Exception as e:
        print(f"❌ SEC filing parse error: {e}")

    return None, None

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    cik, matched_name = resolve_cik(company_name)
    if not cik:
        return {"error": f"Unable to resolve CIK for {company_name}"}

    q_accession, q_primary_doc = get_latest_filing(cik, "10-Q")
    k_accession, k_primary_doc = get_latest_filing(cik, "10-K")

    q_urls = get_actual_filing_urls(cik, q_accession, q_primary_doc, "10-Q") if q_accession else {}
    k_urls = get_actual_filing_urls(cik, k_accession, k_primary_doc, "10-K") if k_accession else {}

    push_new_aliases_to_github()

    return {
        "Matched Company Name": matched_name,
        "CIK": cik,
        "10-Q Filing": q_urls.get("HTML Report") or "No recent 10-Q found",
        "10-K Filing": k_urls.get("HTML Report") or k_urls.get("Excel Report") or "No recent 10-K found"
    }
