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

# === Legacy CIK Resolver Wrapper ===
def resolve_cik(name: str) -> Tuple[str, str]:
    """Dummy legacy fallback."""
    if name.lower() == "rh":
        return ("1528849", "RH")
    return (None, name)

# === Main Resolver ===
def resolve_company_name(name: str) -> Tuple[str, str]:
    name_lower = name.lower()
    aliases = load_alias_map()

    # Normalize alias keys to lowercase
    alias_map = {k.lower(): v for k, v in aliases.items()}

    # Check aliases (case insensitive)
    if name_lower in alias_map:
        resolved = alias_map[name_lower]
        cik, _ = resolve_cik(resolved)
        if cik:
            return resolved, cik.zfill(10)

    # Fuzzy match fallback from SEC ticker list
    try:
        sec_data = requests.get(SEC_TICKER_CIK_URL, headers=HEADERS, timeout=5).json()
        candidates = [
            (entry["ticker"].lower(), entry["title"], str(entry["cik_str"]).zfill(10))
            for entry in sec_data.values()
        ]

        for ticker, title, cik in candidates:
            if name_lower == ticker or name_lower == title.lower():
                return title, cik
    except Exception as e:
        print(f"[Warning] Fuzzy SEC match failed: {e}")

    # Legacy fallback
    cik, resolved = resolve_cik(name)
    if cik:
        return resolved, cik.zfill(10)

    raise ValueError(f"Unable to resolve name: {name}")

# === GitHub Alias Sync ===
def push_new_aliases_to_github():
    """Placeholder: in prod, you'd use GitHub API or git push via subprocess."""
    print("[Info] push_new_aliases_to_github() called – no-op in dev mode")
    # You can implement GitHub push logic here using PyGitHub or subprocess git
