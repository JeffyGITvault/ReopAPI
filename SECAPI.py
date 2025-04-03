from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup
import re
import json
import csv
from datetime import datetime, timedelta
from io import StringIO

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-Q for viewing and 10-K for Excel download. Uses dynamic CIK resolution, alias mapping, and fallback logic.",
    version="v4.2.0"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
CIK_FTP_CSV = "https://www.sec.gov/files/company_tickers.csv"
ALIAS_GITHUB_JSON = "https://raw.githubusercontent.com/JeffyGITvault/ReopAPI/main/alias_map.json"

# Baseline hardcoded aliases
ALIAS_MAP = {
    "meta": "Meta Platforms, Inc.",
    "goog": "Alphabet Inc.",
    "google": "Alphabet Inc.",
    "fb": "Meta Platforms, Inc.",
    "rh": "RH",
    "cent": "Central Garden & Pet Company",
    "ball": "Ball Corporation"
}

CIK_CACHE = {}
NEW_ALIASES = {}


def load_cik_cache():
    try:
        resp = requests.get(CIK_FTP_CSV, headers=HEADERS)
        if resp.status_code == 200:
            content = resp.text
            reader = csv.DictReader(StringIO(content))
            for row in reader:
                ticker = row['ticker'].lower().strip()
                title = row['title'].strip()
                cik = str(row['cik_str']).zfill(10)
                CIK_CACHE[ticker] = {"cik": cik, "name": title}
    except Exception as e:
        print(f"Failed to load CIK cache: {e}")


load_cik_cache()


def load_aliases_from_github():
    try:
        response = requests.get(ALIAS_GITHUB_JSON, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            remote_aliases = response.json()
            ALIAS_MAP.update(remote_aliases)
            print(f"🔁 Loaded {len(remote_aliases)} remote aliases")
        else:
            print("⚠️ Failed to fetch alias_map.json")
    except Exception as e:
        print(f"⚠️ Alias fetch error: {e}")


load_aliases_from_github()


def record_alias(user_input: str, resolved_name: str):
    if user_input.lower() not in ALIAS_MAP:
        NEW_ALIASES[user_input.lower()] = resolved_name
        print(f"🆕 Learned alias: {user_input.lower()} → {resolved_name}")


def resolve_cik(company_name: str):
    original_name = company_name
    name_key = company_name.lower().strip()
    resolved_name = ALIAS_MAP.get(name_key, company_name)

    if name_key in CIK_CACHE:
        record_alias(company_name, CIK_CACHE[name_key]['name'])
        return CIK_CACHE[name_key]['cik'], CIK_CACHE[name_key]['name']

    cleaned = re.sub(r'(,?\s+(Inc|Corp|Corporation|LLC|Ltd)\.?)$', '', resolved_name, flags=re.IGNORECASE)
    query = cleaned.replace(" ", "+")
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={query}&match=contains&action=getcompany"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return None, resolved_name

    soup = BeautifulSoup(resp.text, "html.parser")
    cik_tag = soup.find("a", href=True, string=lambda x: x and x.isdigit())
    if cik_tag:
        cik = cik_tag.text.strip().zfill(10)
        record_alias(company_name, resolved_name)
        return cik, resolved_name
    return None, resolved_name


def validate_url(url):
    try:
        resp = requests.head(url, headers=HEADERS)
        return resp.status_code == 200
    except:
        return False


def get_actual_filing_urls(cik, accession, primary_doc):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"
    report_url = base_url + primary_doc if primary_doc and primary_doc.endswith(".htm") else None
    excel_url = None

    resp = requests.get(index_url, headers=HEADERS)
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a"):
            href = a.get("href", "").lower()
            if not href:
                continue
            full_url = f"https://www.sec.gov{href}"
            if not report_url and href.endswith(".htm") and ("10q" in href or "10-k" in href):
                report_url = full_url
            if href.endswith("financial_report.xlsx") and validate_url(full_url):
                excel_url = full_url

    return {
        "10-K/10-Q Index Page": index_url,
        "Full HTML Filing Report": report_url,
        "Financial Report (Excel)": excel_url
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
        except Exception:
            continue
    return None, None


@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    cik, matched_name = resolve_cik(company_name)
    if not cik:
        return {"error": f"Unable to resolve CIK for {company_name}"}

    q_accession, q_primary_doc = get_latest_filing(cik, "10-Q")
    k_accession, k_primary_doc = get_latest_filing(cik, "10-K")

    q_urls = get_actual_filing_urls(cik, q_accession, q_primary_doc) if q_accession else {}
    k_urls = get_actual_filing_urls(cik, k_accession, k_primary_doc) if k_accession else {}

    return {
        "Matched Company Name": matched_name,
        "CIK": cik,
        "10-Q Filing": q_urls if q_urls else "No recent 10-Q found",
        "10-K Excel": k_urls.get("Financial Report (Excel)") if k_urls else "No recent 10-K Excel found"
    }
