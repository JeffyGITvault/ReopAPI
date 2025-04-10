import json
import os
import time
import csv
import requests
from io import StringIO
from bs4 import BeautifulSoup
import re
from dotenv import load_dotenv
from difflib import SequenceMatcher

# === Load .env if present ===
load_dotenv()

# === Configuration ===
HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
SEC_TICKERS_JSON = "https://www.sec.gov/files/company_tickers.json"
SEC_TICKERS_CSV = "https://www.sec.gov/files/company_tickers.csv"
ALIAS_GITHUB_JSON = "https://raw.githubusercontent.com/JeffyGITvault/ReopAPI/main/alias_map.json"
ALIAS_LOCAL_JSON = "alias_map.json"
ALIAS_PUSH_URL = "https://api.github.com/repos/JeffyGITvault/ReopAPI/contents/alias_map.json"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# === In-Memory Stores ===
CIK_CACHE = {}
ALIAS_MAP = {
    "meta": "Meta Platforms, Inc.",
    "goog": "Alphabet Inc.",
    "google": "Alphabet Inc.",
    "fb": "Meta Platforms, Inc.",
    "rh": "RH",
    "cent": "Central Garden & Pet Company",
    "ball": "Ball Corporation"
}
PROTECTED_ALIASES = {"meta", "facebook", "google", "alphabet", "fb"}
NEW_ALIASES = {}
ALIAS_TIMESTAMP = {}
ALIAS_TTL = 60 * 60 * 24 * 7  # 1 week

# === Loaders ===
def load_company_tickers_json():
    try:
        resp = requests.get(SEC_TICKERS_JSON, headers=HEADERS)
        if resp.status_code == 200:
            return {v['ticker'].lower(): {
                "cik": str(v['cik_str']).zfill(10),
                "title": v['title']
            } for v in resp.json().values()}
    except Exception as e:
        print(f"⚠️ JSON CIK load error: {e}")
    return {}

def load_aliases():
    def apply_aliases(source_name, aliases):
        for key, val in aliases.items():
            if key in PROTECTED_ALIASES:
                print(f"🔒 Skipping protected alias: '{key}' from {source_name}")
                continue
            if key in ALIAS_MAP and ALIAS_MAP[key] != val:
                print(f"⚠️ {source_name} alias override: '{key}' was '{ALIAS_MAP[key]}', now '{val}'")
            ALIAS_MAP[key] = val

    try:
        if os.path.exists(ALIAS_LOCAL_JSON):
            with open(ALIAS_LOCAL_JSON, "r") as f:
                local_aliases = json.load(f)
                apply_aliases("Local", local_aliases)
    except Exception as e:
        print(f"⚠️ Failed to load local alias_map.json: {e}")

    try:
        response = requests.get(ALIAS_GITHUB_JSON, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            remote_aliases = response.json()
            apply_aliases("Remote", remote_aliases)
            print(f"🔁 Loaded {len(remote_aliases)} remote aliases")
        else:
            print("⚠️ Failed to fetch alias_map.json from GitHub")
    except Exception as e:
        print(f"⚠️ Alias fetch error: {e}")

def init_cache():
    global CIK_CACHE
    CIK_CACHE = load_company_tickers_json()
    load_aliases()

# === Fuzzy Matcher ===
def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

# === Alias Recorder ===
def record_alias(user_input: str, resolved_name: str):
    alias_key = user_input.lower()
    if alias_key in PROTECTED_ALIASES:
        return
    now = time.time()
    if alias_key not in ALIAS_MAP or (alias_key in ALIAS_TIMESTAMP and now - ALIAS_TIMESTAMP[alias_key] > ALIAS_TTL):
        NEW_ALIASES[alias_key] = resolved_name
        ALIAS_TIMESTAMP[alias_key] = now
        print(f"🆕 Learned alias: {alias_key} → {resolved_name}")

# === Core Resolver ===
def resolve_cik(company_name: str):
    name_key = company_name.lower().strip()

    # Priority 1: Exact ticker match
    if name_key in CIK_CACHE:
        data = CIK_CACHE[name_key]
        record_alias(company_name, data['title'])
        return data['cik'], data['title']

    # Priority 2: Alias map lookup
    resolved_name = ALIAS_MAP.get(name_key, company_name)

    # Priority 3: Fuzzy match against SEC titles
    for data in CIK_CACHE.values():
        if similar(name_key, data['title']) >= 0.8:
            record_alias(company_name, data['title'])
            return data['cik'], data['title']

    # Priority 4: Last-resort web scrape fallback
    cleaned = re.sub(r'(,?\s+(Inc|Corp|Corporation|LLC|Ltd)\.?$)', '', resolved_name, flags=re.IGNORECASE)
    query = cleaned.replace(" ", "+")
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={query}&match=contains&action=getcompany"
    try:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            cik_tag = soup.find("a", href=True, string=lambda x: x and x.isdigit())
            if cik_tag:
                cik = cik_tag.text.strip().zfill(10)
                record_alias(company_name, resolved_name)
                return cik, resolved_name
    except Exception as e:
        print(f"⚠️ Web fallback failed: {e}")

    return None, company_name

# === Initialize Cache on Import ===
init_cache()
