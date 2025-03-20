from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-K, 10-Q, and Financial Report for any public company.",
    version="v3.1.2"
)

HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"message": "SEC API is live!"}

def get_cik(company_name):
    """
    Searches the SEC database for a company's CIK (Central Index Key).
    Ensures that the correct company is selected.
    """
    search_url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={company_name.replace(' ', '+')}&match=contains&action=getcompany"
    response = requests.get(search_url, headers=HEADERS)

    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    cik_element = soup.find("span", class_="companyMatch")

    if cik_element:
        cik = cik_element.text.strip().zfill(10)  # Ensure 10-digit CIK format
        print(f"Selected CIK for {company_name}: {cik}")  # Debug log
        return cik
    else:
        print(f"CIK not found for {company_name}")
        return None
   
def get_actual_filing_urls(index_url):
    """
    Parses the SEC index.html page and extracts direct links to:
    - The full 10-K and 10-Q report (.htm)
    - The Financial_Report.xlsx file (if available)
    """
    response = requests.get(index_url, headers=HEADERS)
    if response.status_code != 200:
        return {"error": "Failed to fetch SEC index page"}

    soup = BeautifulSoup(response.text, "html.parser")

    ten_k_htm_url = None
    ten_q_htm_url = None
    financial_report_url = None

    for link in soup.find_all("a"):
        href = link.get("href")

        if href:
            # Extract the correct 10-K and 10-Q document
            if "10-k" in href.lower() and href.lower().endswith(".htm"):
                if "summary" not in href.lower() and "index" not in href.lower():
                    ten_k_htm_url = f"https://www.sec.gov{href}"

            if "10-q" in href.lower() and href.lower().endswith(".htm"):
                if "summary" not in href.lower() and "index" not in href.lower():
                    ten_q_htm_url = f"https://www.sec.gov{href}"

    return {
        "10-K Report": ten_k_htm_url if ten_k_htm_url else "Not Found",
        "10-Q Report": ten_q_htm_url if ten_q_htm_url else "Not Found",
        "Financial Report (Excel)": financial_report_url if financial_report_url else "Not Found"
    }

def get_filings(cik):
    """
    Fetches the latest 10-K and 10-Q filings for a given CIK.
    Ensures SEC response is properly handled.
    """
    cik = cik.zfill(10)  # ✅ Always ensure CIK is 10 digits
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"SEC API error: {response.status_code} - {response.text}")  # Debug log
        return {"error": f"Failed to retrieve filings for CIK {cik}"}

    try:
        data = response.json()
    except Exception as e:
        print(f"Error parsing SEC JSON response: {e}")  # Debug log
        return {"error": "Invalid SEC JSON response"}

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    accession_numbers = filings.get("accessionNumber", [])

    # ✅ Handle missing or empty filings list
    if not forms or not accession_numbers:
        return {"error": "No recent filings found"}

    ten_k_index_url = None
    ten_q_index_url = None

    # ✅ Extract latest 10-K and 10-Q filings
    for i, form in enumerate(forms):
        try:
            accession_number = accession_numbers[i].replace("-", "")  # ✅ Format accession number
            if form == "10-K" and not ten_k_index_url:
                ten_k_index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number}/index.html"
            elif form == "10-Q" and not ten_q_index_url:
                ten_q_index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number}/index.html"
        except Exception as e:
            print(f"Error processing filings for CIK {cik}: {e}")  # Debug log

        if ten_k_index_url and ten_q_index_url:
            break

    filing_data = {
        "Company CIK": cik,
        "10-K Index Page": ten_k_index_url if ten_k_index_url else "Not Found",
        "10-Q Index Page": ten_q_index_url if ten_q_index_url else "Not Found",
    }

    # Fetch actual file links if available
    if ten_k_index_url:
        filing_data.update(get_actual_filing_urls(ten_k_index_url))

    if ten_q_index_url:
        filing_data.update(get_actual_filing_urls(ten_q_index_url))

    return filing_data

# ✅ FIXED: Explicitly define the FastAPI route to prevent 404 errors
@app.get("/get_filings/{company_name}", response_model=dict)
async def get_company_filings(company_name: str):
    """
    API endpoint to fetch 10-K and 10-Q filings for any public company.
    """
    cik = get_cik(company_name)

    if not cik:
        return {"error": f"Company '{company_name}' not found in SEC database"}

    return get_filings(cik)
