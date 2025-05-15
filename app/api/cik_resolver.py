# === Standard Library ===
import json
import os
import time
import logging
from typing import Tuple, Dict, Optional, NamedTuple
from functools import lru_cache
from dataclasses import dataclass
from enum import Enum, auto
import re

# === Third-Party Libraries ===
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# === Setup Logging ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# === Constants ===
SEC_TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
GITHUB_ALIAS_JSON = "https://raw.githubusercontent.com/JeffyGITvault/ReopAPI/refs/heads/main/alias_map.json"
LOCAL_ALIAS_FILE = "alias_map.json"
HEADERS = {"User-Agent": "Jeffrey Guenthner (jeffrey.guenthner@gmail.com)"}
REQUEST_TIMEOUT = 5
CACHE_TTL = 3600  # 1 hour in seconds
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

class ResolutionError(Exception):
    """Custom exception for CIK resolution errors."""
    pass

class ResolutionSource(Enum):
    """Source of the resolved company information."""
    ALIAS_MAP = auto()
    SEC_DATA = auto()
    FALLBACK = auto()

@dataclass
class ResolutionResult:
    """Result of company name resolution."""
    official_name: str
    cik: str
    source: ResolutionSource
    confidence: float  # 0.0 to 1.0

# === Global Alias Map Cache ===
_alias_map: Dict[str, str] = {}
_last_load_time: float = 0
_load_attempts: int = 0

def _normalize_key(key: str) -> str:
    """Normalize a key by converting to lowercase and stripping whitespace."""
    return key.lower().strip()

def _retry_on_failure(func):
    """Decorator to retry a function on failure."""
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                    logger.warning(f"Retry {attempt + 1}/{MAX_RETRIES} for {func.__name__}: {e}")
        raise last_exception
    return wrapper

@lru_cache(maxsize=128)
@_retry_on_failure
def _fetch_sec_data() -> Dict:
    """Fetch and cache SEC company data."""
    try:
        response = requests.get(SEC_TICKER_CIK_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch SEC data: {e}")
        raise ResolutionError(f"Failed to fetch SEC data: {e}")

def load_alias_map(force_reload: bool = False) -> Dict[str, str]:
    """
    Load the alias map from GitHub or local file.
    
    Args:
        force_reload: If True, forces reload of the alias map regardless of cache status
        
    Returns:
        Dict containing the alias mappings
        
    Raises:
        ResolutionError: If loading fails after all retries
    """
    global _alias_map, _last_load_time, _load_attempts
    
    current_time = time.time()
    
    # Return cached version if not expired and not forced to reload
    if _alias_map and not force_reload and (current_time - _last_load_time) < CACHE_TTL:
        return _alias_map

    _load_attempts += 1
    last_exception = None

    try:
        logger.info(f"Attempting to fetch alias map from GitHub: {GITHUB_ALIAS_JSON}")
        response = requests.get(GITHUB_ALIAS_JSON, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            _alias_map = {_normalize_key(k): v for k, v in response.json().items()}
            _last_load_time = current_time
            logger.info(f"Loaded {len(_alias_map)} aliases from GitHub")
            print("Alias map loaded with keys:", list(_alias_map.keys())[:5])
            return _alias_map
        else:
            logger.warning(f"GitHub alias map fetch failed with status: {response.status_code}")
    except Exception as e:
        last_exception = e
        logger.error(f"Exception loading alias map from GitHub: {e}")

    # Fallback to local file if GitHub fails
    if os.path.exists(LOCAL_ALIAS_FILE):
        try:
            with open(LOCAL_ALIAS_FILE, "r") as f:
                _alias_map = {_normalize_key(k): v for k, v in json.load(f).items()}
                _last_load_time = current_time
                logger.info(f"Loaded {len(_alias_map)} aliases from local file")
                print("Alias map loaded with keys:", list(_alias_map.keys())[:5])
                return _alias_map
        except Exception as e:
            last_exception = e
            logger.error(f"Failed to load local alias map: {e}")

    logger.error("No alias map loaded from GitHub or local fallback")
    if last_exception:
        raise ResolutionError(f"Failed to load alias map: {last_exception}")
    _alias_map = {}
    return _alias_map

def resolve_company_name(name: str) -> Tuple[str, str]:
    """
    Resolve a company name or ticker to its official name and CIK.
    
    Args:
        name: Company name or ticker to resolve
        
    Returns:
        Tuple of (official_name, cik)
        
    Raises:
        ResolutionError: If the company name cannot be resolved
    """
    try:
        aliases = load_alias_map()
        name_lower = _normalize_key(name)

        # 1. Direct alias match
        resolved = aliases.get(name_lower, name)
        if resolved != name:
            logger.info(f"Found alias match: {name} -> {resolved}")

        # 2. Try SEC-provided company_tickers.json to resolve CIK
        try:
            sec_data = _fetch_sec_data()
            for entry in sec_data.values():
                ticker = _normalize_key(entry["ticker"])
                title = entry["title"]
                cik = str(entry["cik_str"]).zfill(10)

                if resolved.lower() == ticker or resolved.lower() == title.lower():
                    logger.info(f"Found SEC match: {resolved} -> {title} (CIK: {cik})")
                    return title, cik
        except Exception as e:
            logger.warning(f"SEC CIK match failed for '{resolved}': {e}")

        raise ResolutionError(f"Unable to resolve name: {name}")
    except Exception as e:
        logger.error(f"Resolution failed for '{name}': {e}")
        raise ResolutionError(f"Failed to resolve company name: {e}")

def push_new_aliases_to_github() -> None:
    """Placeholder for future implementation of GitHub alias sync."""
    logger.warning("GitHub alias sync not implemented")
    pass

# === Monitoring Functions ===
def get_resolver_stats() -> Dict:
    """Get statistics about the resolver's performance and state."""
    return {
        "alias_map_size": len(_alias_map),
        "last_load_time": _last_load_time,
        "load_attempts": _load_attempts,
        "cache_age": time.time() - _last_load_time if _last_load_time else None,
        "sec_data_cache_size": _fetch_sec_data.cache_info().currsize
    }

from app.api.agents.agent1_fetch_sec import _meta_cache, _html_cache
_meta_cache.clear()
_html_cache.clear()
