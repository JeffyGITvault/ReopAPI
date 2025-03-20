from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-K, 10-Q, and Financial Report for any public company.",
    version="v3.0.0"
)

HEADERS = {"User-Agent": "Jeffrey Geunthner (jeffrey.guenthner@email.com)"}

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"message": "SEC API is live!"}

def get_cik(company_name):
    """
    Searches the SEC database for a company's CIK (Central Index Key).
    If multiple results exist, selects the most relevant match.
    """
    search_url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={company_name.replace(' ', '+')}&match=contains&action=getcompany"
    response = requests.get(search_url, headers=HEADERS)

    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Find all company rows in the SEC search result
    rows = soup.find_all("tr")

    for row in rows:
        cols = row.find_all("td")
        if len(cols) > 1:
            name = cols[0].text.strip().lower()
            cik_link = cols[1].find("a")

            # Debugging: Print extracted company names to check what's found
            print(f"Found company: {name}, CIK: {cik_link.text.strip() if cik_link else 'No CIK'}")

            # Check if the company name closely matches the search query
            if company_name.lower() in name and cik_link:
                cik = cik_link.text.strip().zfill(10)  # Ensure 10-digit CIK format
                return cik

    return None  # If no valid CIK is found

    soup = BeautifulSoup(response.text, "html.parser")

    # Find all company rows in the SEC search result
    rows = soup.find_all("tr")

    for row in rows:
        cols = row.find_all("td")
        if len(cols) > 1:
            name = cols[0].text.strip().lower()
            cik_link = cols[1].find("a")

            # Check if the company name closely matches the search query
            if company_name.lower() in name and cik_link:
                cik = cik_link.text.strip().zfill(10)  # Ensure 10-digit CIK format
                return cik

    return None  # If no valid CIK is found

    soup = BeautifulSoup(response.text, "html.parser")

    # Find all company names in the search results
    company_results = soup.find_all("tr")

    for row in company_results:
        columns = row.find_all("td")
        if len(columns) > 1:
            name = columns[0].text.strip().lower()
            cik_link = columns[1].find("a")

            # Check if the company name closely matches the search query
            if company_name.lower() in name and cik_link:
                cik = cik_link.text.strip().zfill(10)  # Ensure 10-digit CIK format
                return cik

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

            # Find the Financial Report Excel file
            if "Financial_Report.xlsx" in href:
                financial_report_url = f"https://www.sec.gov{href}"

    return {
        "10-K Report": ten_k_htm_url if ten_k_htm_url else "Not Found",
        "10-Q Report": ten_q_htm_url if ten_q_htm_url else "Not Found",
        "Financial Report (Excel)": financial_report_url if financial_report_url else "Not Found"
    }

def get_filings(cik):
    """
    Fetches the latest 10-K and 10-Q filings for a given CIK.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        return {"error": f"Failed to retrieve filings for CIK {cik}"}

    data = response.json()
    filings = data["filings"]["recent"]

    if not filings["form"]:
        return {"error": "No recent filings found"}

    ten_k_index_url = None
    ten_q_index_url = None

    for i, form in enumerate(filings["form"]):
        if form == "10-K" and not ten_k_index_url:
            ten_k_index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{filings['accessionNumber'][i].replace('-', '')}/index.html"
        elif form == "10-Q" and not ten_q_index_url:
            ten_q_index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{filings['accessionNumber'][i].replace('-', '')}/index.html"

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

@app.get("/get_filings/{company_name}")
def get_company_filings(company_name: str):
    """
    API endpoint to fetch 10-K and 10-Q filings for any public company.
    """
    cik = get_cik(company_name)

    if not cik:
        return {"error": f"Company '{company_name}' not found in SEC database"}

    return get_filings(cik)
