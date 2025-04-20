# === Standard Library ===
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# === Third-Party Libraries ===
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI

# === Local Modules ===
from cik_resolver import resolve_cik, push_new_aliases_to_github

app = FastAPI(
    title="Get SEC Filings Data",
    description="Fetches the latest 10-Q filings for a company. Uses CIK resolution, alias mapping, and GitHub-based alias updates. Returns the most recent 10-Q HTML reports.",
    version="v4.3.3"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
MAX_PARALLEL = 10

def validate_url(url):
    try:
        resp = requests.head(url, headers=HEADERS, timeout=2)
        if resp.status_code == 200:
            return True
    except:
        pass

    try:
        resp = requests.get(url, headers=HEADERS, stream=True, timeout=3)
        return resp.status_code == 200
    except:
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

@app.get("/get_quarterlies/{company_name}")
def get_quarterly_filings(company_name: str, count: int = 2):
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
            print(f"[WARN] No recent 10-Qs found for {matched_name} ({cik})")
            return {
                "Matched Company Name": matched_name,
                "CIK": cik,
                "10-Q Filings": []
            }

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

        quarterly_reports = []
        with ThreadPoolExecutor(max_workers=min(len(top_indices), MAX_PARALLEL)) as executor:
            results = list(executor.map(fetch_filing, top_indices))
            quarterly_reports.extend(results)

        for i, report in enumerate(quarterly_reports, start=1):
            report["DisplayIndex"] = f"{i}"
            report["Marker"] = "📌 Most Recent" if i == 1 else "🕓 Older"

        if quarterly_reports:
            print(f"[DEBUG] Raw first result: {repr(quarterly_reports[0])}")

        print(f"[TIMING] Total duration: {round(time.time() - start_time, 2)}s for {company_name}")

        try:
            push_new_aliases_to_github()
        except Exception as e:
            print(f"[Warning] Alias push failed: {e}")

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
