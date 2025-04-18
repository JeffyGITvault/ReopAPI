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
import base64

# === Load .env if present ===
load_dotenv()

# === Configuration ===
HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
SEC_TICKERS_JSON = "https://www.sec.gov/files/company_tickers.json"
ALIAS_GITHUB_JSON = "https://raw.githubusercontent.com/JeffyGITvault/ReopAPI/main/alias_map.json"
ALIAS_LOCAL_JSON = "alias_map.json"
ALIAS_PUSH_URL = "https://api.github.com/repos/JeffyGITvault/ReopAPI/contents/alias_map.json"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# === In-Memory Stores ===
CIK_CACHE = {}
ALIAS_MAP = {}
NEW_ALIASES = {}
ALIAS_TIMESTAMP = {}
ALIAS_TTL = 60 * 60 * 24 * 7  # 1 week

# === Loaders ===
def load_company_tickers_json():
    try:
        resp = requests.get(SEC_TICKERS_JSON, headers=HEADERS, timeout=5)
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
        count = 0
        for key, val in aliases.items():
            key = key.strip().lower()
            val = val.strip()
            if key not in ALIAS_MAP:
                ALIAS_MAP[key] = val
                count += 1
        print(f"✅ Loaded {count} aliases from {source_name}")

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
            apply_aliases("GitHub", remote_aliases)
        else:
            print("⚠️ Failed to fetch alias_map.json from GitHub")
    except Exception as e:
        print(f"⚠️ Alias fetch error: {e}")

def init_cache():
    global CIK_CACHE
    CIK_CACHE = load_company_tickers_json()
    print(f"✅ CIK_CACHE loaded with {len(CIK_CACHE)} entries")
    load_aliases()

# === Fuzzy Matcher ===
def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

# === Alias Recorder ===
def record_alias(user_input: str, resolved_name: str):
    alias_key = user_input.lower().strip()
    if alias_key in ALIAS_MAP:
        return
    if alias_key == resolved_name.lower().strip():
        return
    now = time.time()
    if alias_key not in ALIAS_TIMESTAMP or (now - ALIAS_TIMESTAMP[alias_key] > ALIAS_TTL):
        NEW_ALIASES[alias_key] = resolved_name
        ALIAS_TIMESTAMP[alias_key] = now
        print(f"🆕 Learned alias: {alias_key} → {resolved_name}")

# === Push Alias Deltas to GitHub ===
def push_new_aliases_to_github(retries=2):
    if not NEW_ALIASES:
        print("🔇 No new aliases to push.")
        return
    if not GITHUB_TOKEN:
        print("⚠️ No GitHub token available — skipping alias push.")
        return

    for attempt in range(retries):
        try:
            headers = {
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json"
            }

            get_resp = requests.get(ALIAS_PUSH_URL, headers=headers, timeout=5)
            if get_resp.status_code != 200:
                print(f"⚠️ Could not retrieve alias_map.json: {get_resp.status_code}")
                return

            sha = get_resp.json().get("sha")
            current_content = requests.get(ALIAS_GITHUB_JSON, headers=HEADERS, timeout=5).json()

            updated = {**current_content, **NEW_ALIASES}
            encoded = base64.b64encode(json.dumps(updated, indent=2).encode("utf-8")).decode("utf-8")
            commit_payload = {
                "message": "🔁 Update alias_map.json with learned aliases",
                "content": encoded,
                "sha": sha
            }

            put_resp = requests.put(ALIAS_PUSH_URL, headers=headers, json=commit_payload, timeout=5)
            if put_resp.status_code in [200, 201]:
                print("✅ GitHub alias_map.json updated successfully")
                return
            else:
                print(f"❌ GitHub update failed: {put_resp.status_code}")
        except Exception as e:
            print(f"❌ Alias push error (attempt {attempt + 1}): {e}")
            time.sleep(2)

# === Core Resolver ===
def resolve_cik(company_name: str):
    name_key = company_name.lower().strip()

    if name_key in CIK_CACHE:
        data = CIK_CACHE[name_key]
        print(f"[CIK] Exact ticker match: {company_name} → {data['title']}")
        record_alias(company_name, data['title'])
        return data['cik'], data['title']

    resolved_name = ALIAS_MAP.get(name_key, company_name).strip()
    resolved_key = resolved_name.lower()

    for data in CIK_CACHE.values():
        if data['title'].lower() == resolved_key:
            print(f"[CIK] Exact title match: {company_name} → {data['title']}")
            record_alias(company_name, data['title'])
            return data['cik'], data['title']

    best_match = None
    best_score = 0.0
    for data in CIK_CACHE.values():
        score = similar(resolved_name, data['title'])
        if score >= 0.85 and score > best_score:
            best_match = data
            best_score = score

    if best_match:
        print(f"[CIK] Fuzzy match: {company_name} → {best_match['title']} (score: {best_score:.2f})")
        record_alias(company_name, best_match['title'])
        return best_match['cik'], best_match['title']

    cleaned = re.sub(r'(,?\s+(Inc|Corp|Corporation|LLC|Ltd)\.?$)', '', resolved_name, flags=re.IGNORECASE)
    query = cleaned.replace(" ", "+")
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={query}&match=contains&action=getcompany"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            cik_tag = soup.find("a", href=True, string=lambda x: x and x.isdigit())
            if cik_tag:
                cik = cik_tag.text.strip().zfill(10)
                print(f"[CIK] Web fallback resolved: {company_name} → {resolved_name} (CIK: {cik})")
                record_alias(company_name, resolved_name)
                return cik, resolved_name
    except Exception as e:
        print(f"⚠️ Web fallback failed: {e}")

    print(f"[CIK] No match found for: {company_name}")
    return None, company_name

# === Initialize Cache on Import ===
init_cache()
