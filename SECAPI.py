from fastapi import FastAPI
import re
import requests
from bs4 import BeautifulSoup
from fuzzywuzzy import process

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-K, 10-Q, and Financial Report for any public company.",
    version="v3.2.4"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"message": "SEC API is live!"}

@app.get("/get_cik/{company_name}", response_model=dict)
async def get_cik_route(company_name: str):
    """
    API endpoint to fetch the CIK for a given company.
    """
    cik_data = get_cik(company_name)

    if not cik_data or "CIK" not in cik_data:
        return {"error": f"Company '{company_name}' not found in SEC database"}

    return cik_data

@app.get("/get_filings/{company_name}", response_model=dict)
async def get_company_filings(company_name: str):
    """
    API endpoint to fetch 10-K and 10-Q filings for any public company.
    """
    cik_data = get_cik(company_name)

    if not cik_data or "CIK" not in cik_data:
        return {"error": f"Company '{company_name}' not found in SEC database"}

    cik = cik_data["CIK"]
    return get_filings(cik, cik_data["Normalized Company Name"])

def get_cik(company_name):
    """
    Searches the SEC database for a company's CIK (Central Index Key).
    Fixes SEC table parsing and fuzzy matching.
    """
    HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
    
    # ✅ Normalize company name (handle 'Inc.', 'Corp.', '&' encoding)
    cleaned_name = re.sub(r"( Corp\.?| Inc\.?| Ltd\.?| LLC\.?)$", "", company_name, flags=re.IGNORECASE).strip()
    cleaned_name = cleaned_name.replace("&", "%26")  # ✅ Fix AT&T encoding

    # ✅ SEC search URL
    search_url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={cleaned_name.replace(' ', '+')}&match=contains&action=getcompany"
    
    response = requests.get(search_url, headers=HEADERS)
    if response.status_code != 200:
        return {"error": f"Failed to retrieve SEC data for {company_name}"}

    soup = BeautifulSoup(response.text, "html.parser")

    # ✅ Extract company names and CIKs from the SEC table
    company_names = []
    cik_numbers = []

    for row in soup.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) > 1:
            sec_name = cols[0].text.strip()  # ✅ Company Name
            cik_link = cols[1].find("a")  # ✅ CIK is inside <a> tag

            if cik_link:
                cik = cik_link.text.strip().zfill(10)
                company_names.append(sec_name)
                cik_numbers.append(cik)

    if not company_names:
        return {"error": f"Company '{company_name}' not found in SEC database"}

    # ✅ Fuzzy match company name to get best result
    best_match, match_score = process.extractOne(company_name, company_names)

    if match_score > 75:  # ✅ Confidence threshold
        cik_index = company_names.index(best_match)
        matched_cik = cik_numbers[cik_index]
        print(f"✔ Matched {company_name} to {best_match} (CIK: {matched_cik}) with {match_score}% confidence")
        return {"CIK": matched_cik, "Normalized Company Name": best_match}

    return {"error": f"Company '{company_name}' not found in SEC database"}

def get_actual_filing_urls(index_url, company_name):
    """
    Parses the SEC index.html page and extracts direct links to:
    - The full 10-Q report (.htm)
    - The Financial_Report.xlsx file (if available)
    """
    response = requests.get(index_url, headers=HEADERS)
    if response.status_code != 200:
        return {"error": "Failed to fetch SEC index page"}

    soup = BeautifulSoup(response.text, "html.parser")

    ten_q_htm_url = None
    financial_report_url = None

    company_abbr = company_name.lower().replace(" ", "").replace(".", "")
    
    for link in soup.find_all("a"):
        href = link.get("href")

        if href:
            if "10-q" in href.lower() and href.lower().endswith(".htm"):
                if "summary" not in href.lower() and "index" not in href.lower():
                    if "x10q" in href.lower() or company_abbr in href.lower():
                        ten_q_htm_url = f"https://www.sec.gov{href}"
          
            if "Financial_Report.xlsx" in href or "financial_report.xlsx" in href.lower():
                financial_report_url = f"https://www.sec.gov{href}"
    
    return {
        "10-Q Report": ten_q_htm_url if ten_q_htm_url else "Not Found",
        "Financial Report (Excel)": financial_report_url if financial_report_url else "Not Found"
    }

def get_filings(cik, company_name=None):
    """
    Fetches the latest 10-K and 10-Q filings for a given CIK.
    Ensures SEC response is properly handled.
    """
    cik = cik.lstrip("0").zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    headers = {
        "User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)",
        "Accept-Encoding": "gzip, deflate",
        "Host": "data.sec.gov",
        "Connection": "keep-alive"
    }
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return {"error": f"Failed to retrieve filings for CIK {cik}"}

    data = response.json()
    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    accession_numbers = filings.get("accessionNumber", [])

    if not forms or not accession_numbers:
        return {"error": f"No recent filings found for CIK {cik}"}

    ten_k_index_url = None
    ten_q_index_url = None

    for i, form in enumerate(forms):
        try:
            accession_number = accession_numbers[i].replace("-", "")
            if form == "10-K" and not ten_k_index_url:
                ten_k_index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number}/index.html"
            elif form == "10-Q" and not ten_q_index_url:
                ten_q_index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number}/index.html"
        except Exception as e:
            print(f"Error processing filings for CIK {cik}: {e}")

        if ten_k_index_url and ten_q_index_url:
            break

    filing_data = {
        "Company CIK": cik,
        "10-K Index Page": ten_k_index_url if ten_k_index_url else "Not Found",
        "10-Q Index Page": ten_q_index_url if ten_q_index_url else "Not Found",
    }

    if ten_k_index_url:
        filing_data.update(get_actual_filing_urls(ten_k_index_url, company_name))

    if ten_q_index_url:
        filing_data.update(get_actual_filing_urls(ten_q_index_url, company_name))

    return filing_data
