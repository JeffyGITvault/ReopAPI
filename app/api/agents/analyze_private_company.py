import logging
import requests
from typing import Dict, Any, Optional
from app.api.config import SEARCH_API_KEY, GOOGLE_CSE_ID

logger = logging.getLogger("analyze_private_company")

def google_search(query: str, num: int = 5) -> str:
    if not SEARCH_API_KEY or not GOOGLE_CSE_ID:
        logger.warning("Google Search API key or CSE ID not set. Skipping Google fetch.")
        return "Google Search API key or CSE ID not set."
    try:
        params = {
            "key": SEARCH_API_KEY,
            "cx": GOOGLE_CSE_ID,
            "q": query,
            "num": num
        }
        response = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=10)
        response.raise_for_status()
        items = response.json().get("items", [])
        if not items:
            return "No public web results found."
        return "\n".join([
            f"- [{item['title']}]({item['link']}) — {item.get('snippet', 'No snippet')}"
            for item in items
        ])
    except Exception as e:
        logger.warning(f"Google Search API fetch failed for query '{query}': {e}")
        return f"Google Search API fetch failed: {str(e)}"

def analyze_private_company(company_name: str, meeting_context: str, additional_context: Optional[dict] = None) -> Dict[str, Any]:
    """
    Agent for private companies: Gathers public web signals, news, and industry data.
    Returns a dict matching the private_company_analysis schema.
    """
    try:
        # Company overview
        overview_query = f'"{company_name}" overview OR about OR company site:linkedin.com OR site:crunchbase.com'
        overview = google_search(overview_query, num=3)
        if not overview or 'No public web results found.' in overview or 'API key' in overview:
            overview = f"Overview for {company_name} (private): No public overview found."
        # Recent news
        news_query = f'"{company_name}" news OR press release OR announcement'
        news = google_search(news_query, num=5)
        if not news or 'No public web results found.' in news or 'API key' in news:
            news = f"Recent news for {company_name}: No recent news found."
        # Key people
        people_query = f'"{company_name}" leadership OR executives OR team site:linkedin.com OR site:crunchbase.com'
        key_people = google_search(people_query, num=5)
        if not key_people or 'No public web results found.' in key_people or 'API key' in key_people:
            key_people = f"Key people at {company_name}: No public key people found."
        # Industry/market positioning
        industry_query = f'"{company_name}" industry OR market positioning OR competitors'
        industry = google_search(industry_query, num=3)
        if not industry or 'No public web results found.' in industry or 'API key' in industry:
            industry = f"Industry/market positioning for {company_name}: No public industry context found."
        # Risks/opportunities
        risks_query = f'"{company_name}" risks OR opportunities OR challenges OR growth'
        risks = google_search(risks_query, num=3)
        if not risks or 'No public web results found.' in risks or 'API key' in risks:
            risks = f"Risks and opportunities for {company_name}: No public risk/opportunity analysis found."
        return {
            "company_overview": overview,
            "recent_news": news,
            "key_people": key_people,
            "industry_positioning": industry,
            "risks_opportunities": risks
        }
    except Exception as e:
        logger.error(f"Private company analysis failed: {e}")
        return {
            "company_overview": f"[ERROR] Private company analysis failed: {str(e)}",
            "recent_news": "",
            "key_people": "",
            "industry_positioning": "",
            "risks_opportunities": ""
        }

def format_table(table_dict):
    if not table_dict:
        return "No data available."
    # If table_dict is already a markdown string, just return it
    if isinstance(table_dict, str):
        return table_dict
    quarters = list(table_dict.keys())
    metrics = set()
    for q in quarters:
        if isinstance(table_dict[q], dict):
            metrics.update(table_dict[q].keys())
        elif isinstance(table_dict[q], list):
            for item in table_dict[q]:
                if ":" in item:
                    metrics.add(item.split(":")[0].strip())
    metrics = sorted(metrics)
    header = "| Metric | " + " | ".join(quarters) + " |\n"
    sep = "|---" * (len(quarters)+1) + "|\n"
    rows = ""
    for m in metrics:
        row = f"| {m} | "
        for q in quarters:
            val = ""
            if isinstance(table_dict[q], dict):
                val = table_dict[q].get(m, "")
            elif isinstance(table_dict[q], list):
                for item in table_dict[q]:
                    if item.startswith(f"{m}:"):
                        val = item.split(":", 1)[1].strip()
            row += f"{val} | "
        rows += row + "\n"
    return header + sep + rows 