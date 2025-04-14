from fastapi import FastAPI
from cik_resolver import resolve_cik, push_new_aliases_to_github
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

app = FastAPI(
    title="Get SEC Filings Data",
    description="Fetches latest 10-Q and 10-K filings. Supports alias learning, GitHub persistence, and clean CIK resolution.",
    version="v4.2.5"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

# === Utility ===
def get_filing_urls(cik, accession, primary_doc):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"
    report_url = base_url + primary_doc if primary_doc and primary_doc.endswith(".htm") else None
    excel_url = None

    try:
        resp = requests.get(index_url, headers=HEADERS)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a"):
                href = a.get("href", "").lower()
                if not href:
                    continue
                full_url = f"https://www.sec.gov{href}"
                if not report_url and href.endswith(".htm") and ("10-k" in href or "10k" in href):
                    report_url = full_url
                if href.endswith(".xlsx") and "financial" in href:
                    excel_url = full_url
                    break
    except Exception as e:
        print(f"⚠️ Filing fetch failed: {e}")

    return report_url, excel_url

def get_latest_filing(cik, form_type):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            return None, None

        data = response.json()
        filings = data.get("filings", {}).get("recent", {})
        form_types = filings.get("form", [])
        accession_numbers = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])
        filing_dates = filings.get("filingDate", [])

        cutoff = datetime.now() - timedelta(days=2*365)  # Shorten to 2 years

        for i, form in enumerate(form_types):
            try:
                filing_date = datetime.strptime(filing_dates[i], "%Y-%m-%d")
                if filing_date < cutoff:
                    continue
                if form == form_type:
                    accession = accession_numbers[i].replace("-", "")
                    return accession, primary_docs[i]
            except Exception as e:
                print(f"⚠️ Date parse error: {e}")
                continue
    except Exception as e:
        print(f"⚠️ Filing lookup failed: {e}")
    return None, None

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    cik, matched_name = resolve_cik(company_name)
    if not cik:
        return {"error": f"Unable to resolve CIK for {company_name}"}

    q_accession, q_primary = get_latest_filing(cik, "10-Q")
    k_accession, k_primary = get_latest_filing(cik, "10-K")

    report_url_q, _ = get_filing_urls(cik, q_accession, q_primary) if q_accession else (None, None)
    _, report_url_k = get_filing_urls(cik, k_accession, k_primary) if k_accession else (None, None)

    push_new_aliases_to_github()

    return {
        "Matched Company Name": matched_name,
        "CIK": cik,
        "10-Q Filing": report_url_q or "❌ Not available",
        "10-K Excel": report_url_k or "❌ Not available"
    }
