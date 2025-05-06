import os
from dotenv import load_dotenv

load_dotenv()

# === API Keys ===
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY")
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

# === SEC URLs ===
SEC_TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

# === GitHub Alias Map ===
GITHUB_ALIAS_JSON = "https://raw.githubusercontent.com/JeffyGITvault/ReopAPI/refs/heads/main/alias_map.json"
LOCAL_ALIAS_FILE = "alias_map.json"

# === HTTP Headers ===
DEFAULT_HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}

# === Timeouts and Caching ===
REQUEST_TIMEOUT = 5
CACHE_TTL = 3600  # 1 hour
MAX_RETRIES = 3
RETRY_DELAY = 1 