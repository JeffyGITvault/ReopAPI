# utils.py
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

def validate_url(url):
    try:
        resp = requests.head(url, headers=HEADERS, timeout=2)
        return resp.status_code == 200
    except:
        return False

def get_actual_filing_url(cik, accession, primary_doc):
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
    index_url = base_url + "index.html"

    if primary_doc and primary_doc.endswith(".htm"):
        html_url = base_url + primary_doc
        if validate_url(html_url):
            return html_url

    try:
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
            full_url = f"https://www.sec.gov{href}"
            if validate_url(full_url):
                return full_url
    except Exception as e:
        print(f"[ERROR] While finding HTML report: {e}")

    return "Unavailable"

def get_actual_filing_urls(cik, form_type="10-Q"):
    """Fetch up to 4 filings of the given type (e.g., '10-Q') for a given CIK."""
    url = f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        filings = data.get("filings", {}).get("recent", {})
        form_types = filings.get("form", [])
        accession_numbers = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])
        filing_dates = filings.get("filingDate", [])

        all_filings = []
        for i, form in enumerate(form_types):
            if form == form_type:
                accession = accession_numbers[i].replace("-", "")
                primary_doc = primary_docs[i]
                html_url = get_actual_filing_url(cik, accession, primary_doc)
                all_filings.append({
                    "filing_date": filing_dates[i],
                    "HTML Report": html_url
                })

        return sorted(all_filings, key=lambda x: x["filing_date"], reverse=True)[:4]
    except Exception as e:
        print(f"[ERROR] Failed to fetch filings from SEC: {e}")
        return []
