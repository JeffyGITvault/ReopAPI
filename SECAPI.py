# === Standard Library ===
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# === Third-Party Libraries ===
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query, Path
from typing import Optional

# === Local Modules ===
from cik_resolver import resolve_company_name, push_new_aliases_to_github, load_alias_map

app = FastAPI(
    title="SECAPI",
    version="4.3.8",
    description="Fetches the latest 10-Q filings for a company. Uses CIK resolution, alias mapping, and GitHub-based alias updates. Returns validated SEC HTML reports."
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
MAX_PARALLEL = 10

@app.get("/debug_alias_map")
def debug_alias_map():
    alias_map = load_alias_map()
    return {
        "alias_count": len(alias_map),
        "example_keys": list(alias_map.keys())[:5]  # optional sanity check
    }

@app.get("/")
def root():
    return {"status": "SECAPI is live"}

def validate_url(url):
    try:
        resp = requests.head(url, headers=HEADERS, timeout=3)
        if resp.status_code == 200:
            return True
    except Exception:
        pass

    try:
        resp = requests.get(url, headers=HEADERS, stream=True, timeout=5)
        return resp.status_code == 200
    except Exception:
        return False

def get_actual_filing_url(cik, accession, primary_doc):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"
    html_url = None

    try:
        if primary_doc and primary_doc.endswith(".htm"):
            html_url = base_url + primary_doc
            if validate_url(html_url):
                return html_url
            else:
                print(f"[WARN] Primary document failed validation: {html_url}")
                html_url = None

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
            else:
                print(f"[INFO] Rejected candidate due to failed validation: {candidate_url}")

    except Exception as e:
        print(f"[ERROR] Exception while resolving filing URL for CIK {cik}: {e}")

    return html_url or "Unavailable"

@app.get("/get_quarterlies/{company_name}")
def get_quarterly_filings(
    company_name: str = Path(..., description="Company name or stock ticker"),
    count: int = Query(2, description="Number of 10-Q filings to return")
):
    start_time = time.time()
    cached = []

    try:
        matched_name, cik = resolve_company_name(company_name)
    except Exception as e:
        return {
            "company_name": company_name,
            "cik": None,
            "filings": [],
            "cached_quarterlies": cached,
            "error": f"CIK resolution failed: {e}"
        }

    url = f"https://data.sec.gov/submissions/CIK{int(cik):010}.json"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            return {
                "company_name": matched_name,
                "cik": cik,
                "filings": [],
                "cached_quarterlies": cached,
                "error": "CIK JSON not found or request failed"
            }

        data = response.json()
        filings = data.get("filings", {}).get("recent", {})
        form_types = filings.get("form", [])
        accession_numbers = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])
        filing_dates = filings.get("filingDate", [])

        all_10q = []
        for i, form in enumerate(form_types):
            if form == "10-Q":
                try:
                    filing_date = datetime.strptime(filing_dates[i], "%Y-%m-%d")
                    all_10q.append((filing_date, i))
                except:
                    continue

        all_10q.sort(reverse=True)
        top_indices = [i for _, i in all_10q[:count]]

        if not top_indices:
            return {
                "company_name": matched_name,
                "cik": cik,
                "filings": [],
                "cached_quarterlies": cached,
                "note": "No recent 10-Qs found"
            }

        def fetch_filing(index):
            accession = accession_numbers[index].replace("-", "")
            primary_doc = primary_docs[index]
            filing_date = filing_dates[index]
            html_url = get_actual_filing_url(cik, accession, primary_doc)

            status = "Validated" if html_url and html_url != "Unavailable" else "Unavailable"
            markdown_link = f"[10-Q Report]({html_url})" if html_url and html_url != "Unavailable" else "Unavailable"

            return {
                "display_index": f"{index + 1}",
                "marker": "📌 Most Recent" if index == 0 else "🕓 Older",
                "filing_date": filing_date,
                "html_url": html_url,
                "html_link": markdown_link,
                "status": status
            }

        quarterly_reports = []
        with ThreadPoolExecutor(max_workers=min(len(top_indices), MAX_PARALLEL)) as executor:
            results = list(executor.map(fetch_filing, top_indices))
            quarterly_reports.extend(results)

        for i, report in enumerate(quarterly_reports, start=1):
            report["display_index"] = f"{i}"
            report["marker"] = "📌 Most Recent" if i == 1 else "🕓 Older"

        if quarterly_reports:
            print(f"[DEBUG] Raw first result: {repr(quarterly_reports[0])}")

        print(f"[TIMING] Total duration: {round(time.time() - start_time, 2)}s for {company_name}")

        try:
            push_new_aliases_to_github()
        except Exception as e:
            print(f"[Warning] Alias push failed: {e}")

        return {
            "company_name": matched_name,
            "cik": cik,
            "filings": quarterly_reports,
            "cached_quarterlies": cached
        }

    except Exception as e:
        print(f"[ERROR] /get_quarterlies failed for {company_name}: {e}")
        return {
            "company_name": company_name,
            "cik": cik,
            "filings": [],
            "cached_quarterlies": cached,
            "error": str(e)
        }
