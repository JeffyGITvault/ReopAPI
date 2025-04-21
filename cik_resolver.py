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
GITHUB_ALIAS_JSON = "https://raw.githubusercontent.com/JeffyGITvault/sec-alias-map/main/alias_map.json"
LOCAL_ALIAS_FILE = "alias_map.json"
HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

# === Load alias map from local and remote ===
def load_alias_map():
    try:
        response = requests.get(GITHUB_ALIAS_JSON, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[Warning] Failed to load GitHub alias map: {e}")

    if os.path.exists(LOCAL_ALIAS_FILE):
        with open(LOCAL_ALIAS_FILE, "r") as f:
            return json.load(f)

    return {}

# === Main Resolver ===
def resolve_company_name(name: str) -> Tuple[str, str]:
    name_lower = name.lower()
    aliases = load_alias_map()

    # Normalize alias keys to lowercase
    alias_map = {k.lower(): v for k, v in aliases.items()}

    # 1. Direct alias match
    if name_lower in alias_map:
        resolved = alias_map[name_lower]
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

# === GitHub Alias Sync ===
def push_new_aliases_to_github():
    """Placeholder: in prod, you'd use GitHub API or git push via subprocess."""
    print("[Info] push_new_aliases_to_github() called – no-op in dev mode")
    # You can implement GitHub push logic here using PyGitHub or subprocess git
