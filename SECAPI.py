# === Standard Library ===
import json
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# === Third-Party Libraries ===
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI

# === Local Modules ===
from cik_resolver import resolve_cik, push_new_aliases_to_github

app = FastAPI(
    title="Get SEC Filings Data",
    description="Fetches the latest 10-Q filings for a company. Uses CIK resolution, alias mapping, and GitHub-based alias updates. Returns up to the most recent 10-Q HTML reports, with optional control over how many filings to retrieve.",
    version="v4.3.1"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
MAX_PARALLEL = 10  # Limit concurrent threads per request

# === Utilities ===
def validate_url(url):
    try:
        # Try HEAD first
        resp = requests.head(url, headers=HEADERS, timeout=2)
        if resp.status_code == 200:
            return True
    except Exception as e:
        print(f"[HEAD FAIL] {url} — {e}")

    # Fallback to GET with stream
    try:
        resp = requests.get(url, headers=HEADERS, stream=True, timeout=3)
        return resp.status_code == 200
    except Exception as e:
        print(f"[GET FAIL] {url} — {e}")
        return False

def get_actual_filing_url(cik, accession, primary_doc):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"
    html_url = None

    try:
        # Try primary_doc first
        if primary_doc and primary_doc.endswith(".htm"):
            html_url = base_url + primary_doc
            if validate_url(html_url):
                return html_url

        # Fallback to best .htm from index
        resp = requests.get(index_url, headers=HEADERS)
        resp.raise_for_status()

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
    count = max(1, min(count, 4)) 
    start_time = time.time()

    cik, matched_name = resolve_cik(company_name)
    if not cik:
        return {
            "Matched Company Name": company_name,
            "CIK": None,
            "10-Q Filings": []
        }

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            return {
                "Matched Company Name": matched_name,
                "CIK": cik,
                "10-Q Filings": []
            }

        data = response.json()
        filings = data.get("filings", {}).get("recent", {})
        form_types = filings.get("form", [])
        accession_numbers = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])
        filing_dates = filings.get("filingDate", [])

        def fetch_filing(index):
            accession = accession_numbers[index].replace("-", "")
            primary_doc = primary_docs[index]
            filing_date = filing_dates[index]
            html_url = get_actual_filing_url(cik, accession, primary_doc)
            status = "Validated" if html_url and html_url != "Unavailable" else "Unavailable"
            return {
                "Filing Date": filing_date,
                "HTML Report": html_url,
                "Status": status
            }

        with ThreadPoolExecutor(max_workers=min(count, MAX_PARALLEL)) as executor:
            futures = []
            for i, form in enumerate(form_types):
                if form == "10-Q":
                    futures.append(executor.submit(fetch_filing, i))
                if len(futures) == count:
                    break

            quarterly_reports = []
            for future in as_completed(futures):
                if len(quarterly_reports) == count:
                    break
                try:
                    result = future.result(timeout=3)
                    if result["HTML Report"] and result["HTML Report"] != "Unavailable":
                        quarterly_reports.append(result)
                    time.sleep(2.0)    
                except Exception as e:
                    print(f"[ERROR] Filing fetch failed: {e}")

        # Add display index for GPT templating (1️⃣, 2️⃣, etc.)
        for i, report in enumerate(quarterly_reports, start=1):
            report["DisplayIndex"] = f"{i}️⃣"
            report["Marker"] = "📌 Most Recent" if i == 1 else "🕓 Older"

        if quarterly_reports:
            print(f"[DEBUG] Raw first result: {repr(quarterly_reports[0])}")

        print(f"[TIMING] Total duration: {round(time.time() - start_time, 2)}s for {company_name}")

        return {
            "Matched Company Name": matched_name,
            "CIK": cik,
            "10-Q Filings": quarterly_reports
        }

    except Exception as e:
        print(f"[ERROR] /get_quarterlies failed for {company_name}: {e}")
        return {
            "Matched Company Name": company_name,
            "CIK": cik,
            "10-Q Filings": []
        }
