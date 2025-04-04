import json
import os
import requests

# === Configuration ===

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
LOCAL_ALIAS_PATH = "alias_map.json"
USER_AGENT_HEADER = {"User-Agent": "MyCompanyName your.email@example.com"}  # <-- Update this

# === Utility Functions ===

def load_company_tickers():
    """Load SEC ticker/CIK data from the SEC website."""
    response = requests.get(SEC_TICKERS_URL, headers=USER_AGENT_HEADER)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch SEC ticker data. Status code: {response.status_code}")
    return response.json()

def load_alias_map(local_path=LOCAL_ALIAS_PATH):
    """Load alias-to-ticker map from a local JSON file."""
    if os.path.exists(local_path):
        with open(local_path, "r") as f:
            return json.load(f)
    else:
        # Create a default alias map and save it
        default_aliases = {
            "restoration hardware": "RH",
            "williams sonoma": "WSM",
            "grocery outlet": "GO",
            "albertsons": "ACI",
            "home depot": "HD",
            "lowes": "LOW",
            "google": "GOOGL",
            "facebook": "META",
            "alphabet": "GOOGL",
            "meta": "META",
            "apple": "AAPL",
            "tesla": "TSLA",
            "boeing": "BA"
        }
        with open(local_path, "w") as f:
            json.dump(default_aliases, f, indent=4)
        return default_aliases

def resolve_cik(input_name, ticker_data, alias_map):
    """Resolve user input to a 10-digit CIK using alias map and SEC ticker data."""
    input_name = input_name.strip().lower()

    # Step 1: Check alias map
    if input_name in alias_map:
        input_name = alias_map[input_name].lower()

    # Step 2: Match by ticker
    for entry in ticker_data.values():
        if entry['ticker'].lower() == input_name:
            return str(entry['cik_str']).zfill(10)

    # Step 3: Match by company title
    for entry in ticker_data.values():
        if entry['title'].lower() == input_name:
            return str(entry['cik_str']).zfill(10)

    return None  # Not found

# === Example Execution ===

if __name__ == "__main__":
    try:
        # Load data
        ticker_data = load_company_tickers()
        alias_map = load_alias_map()

        # Test inputs
        test_inputs = ["Restoration Hardware", "GOOGL", "Meta", "Home Depot", "Tesla", "AAPL"]
        for name in test_inputs:
            cik = resolve_cik(name, ticker_data, alias_map)
            print(f"{name} => CIK: {cik}")

    except Exception as e:
        print(f"Error: {e}")
