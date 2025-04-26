# === Standard Library ===
import json
import os
import time
import csv
import re
import base64
from io import StringIO
from difflib import SequenceMatcher

# === Third-Party Libraries ===
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# === Types ===
from typing import Tuple

# === Constants ===
SEC_TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
GITHUB_ALIAS_JSON = "https://raw.githubusercontent.com/JeffyGITvault/ReopAPI/refs/heads/main/alias_map.json"
LOCAL_ALIAS_FILE = "alias_map.json"
HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

# === Global Alias Map Cache ===
alias_map = {}

# === Load alias map from local and remote ===
def load_alias_map(force_reload=False):
    global ALIAS_MAP

    # Already loaded and no force? Return cached
    if ALIAS_MAP and not force_reload:
        return ALIAS_MAP

    try:
        print(f"[DEBUG] Attempting to fetch alias map from GitHub: {GITHUB_ALIAS_JSON}")
        response = requests.get(GITHUB_ALIAS_JSON, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            ALIAS_MAP = {k.lower(): v for k, v in response.json().items()}
            print(f"[INFO] Loaded {len(ALIAS_MAP)} aliases from GitHub")
            return ALIAS_MAP
        else:
            print(f"[WARNING] GitHub alias map fetch failed with status: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Exception loading alias map from GitHub: {e}")

    # Fallback to local file if GitHub fails
    if os.path.exists(LOCAL_ALIAS_FILE):
        try:
            with open(LOCAL_ALIAS_FILE, "r") as f:
                ALIAS_MAP = {k.lower(): v for k, v in json.load(f).items()}
                print(f"[INFO] Loaded {len(ALIAS_MAP)} aliases from local file")
                return ALIAS_MAP
        except Exception as e:
            print(f"[ERROR] Failed to load local alias map: {e}")

    print("[ERROR] No alias map loaded from GitHub or local fallback")
    ALIAS_MAP = {}
    return ALIAS_MAP

# === Main Resolver ===
def resolve_company_name(name: str) -> Tuple[str, str]:
    aliases = load_alias_map()
    name_lower = name.lower()

    # 1. Direct alias match
    if name_lower in aliases:
        resolved = aliases[name_lower]
    else:
        resolved = name  # fallback to raw input

    # 2. Try SEC-provided company_tickers.json to resolve CIK
    try:
        sec_data = requests.get(SEC_TICKER_CIK_URL, headers=HEADERS, timeout=5).json()
        for entry in sec_data.values():
            ticker = entry["ticker"].lower()
            title = entry["title"]
            cik = str(entry["cik_str"]).zfill(10)

            if resolved.lower() == ticker or resolved.lower() == title.lower():
                return title, cik
    except Exception as e:
        print(f"[Warning] SEC CIK match failed for '{resolved}': {e}")

    raise ValueError(f"Unable to resolve name: {name}")

# === GitHub Alias Sync (Placeholder) ===
def push_new_aliases_to_github():
    """Placeholder: in prod, you'd use GitHub API or git push via subprocess."""
    # No-op for now
    pass
