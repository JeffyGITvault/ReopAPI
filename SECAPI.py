from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup

app = FastAPI(
    title="Get SEC Filings Data",
    description="Retrieves the latest 10-K, 10-Q, and Financial Report for any public company.",
    version="v3.1.0"
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

    # Find all company rows in the SEC search result
    rows = soup.find_all("tr")

    best_match = None

    for row in rows:
        cols = row.find_all("td")
        if len(cols) > 1:
            name = cols[0].text.strip().lower()
            cik_link = cols[1].find("a")  # CIK should be inside an <a> tag

            # Debugging: Print extracted company names in Render logs
            print(f"Found company: {name}, CIK: {cik_link.text.strip() if cik_link else 'No CIK'}")

            # Prioritize exact company name matches
            if company_name.lower() == name and cik_link:
                cik = cik_link.text.strip().zfill(10)  # Ensure 10-digit CIK format
                print(f"Selected CIK for {company_name}: {cik}")  # Debug log
                return cik

            # If no exact match, store the first reasonable match
            if best_match is None and cik_link:
                best_match = cik_link.text.strip().zfill(10)

    # Return best match if no exact match was found
    return best_match if best_match else None

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

     
