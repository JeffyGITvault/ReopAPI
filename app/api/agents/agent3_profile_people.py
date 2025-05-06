# app/api/agents/agent3_profile_people.py

import os
import requests
import logging
from typing import List, Dict, Any
from app.api.groq_client import call_groq
from app.api.config import NEWSDATA_API_KEY, SEARCH_API_KEY, GOOGLE_CSE_ID
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

max_results = 5

def profile_people(people: List[str], company: str) -> List[Dict[str, Any]]:
    """
    Agent 3: Comprehensive profiling using NewsData.io, Groq, and Google enrichment.
    Returns a list of profile dicts for each person.
    """
    if not people:
        return [{"error": "No people provided for profiling."}]

    def build_profile(person: str) -> Dict[str, Any]:
        try:
            profile = {
                "name": person,
                "news_mentions": fetch_newsdata_signals(person, company),
                "role_focus": infer_role_focus(person, company),
                "filing_reference": check_filings_mention(person, company),
                "likely_toolchain": infer_stack_from_job_posts(company),
                "estimated_tenure": estimate_tenure(person),
                "profile_signals": infer_risk_signals(person),
                "public_presence": enrich_with_public_signals(person, company),
                "public_web_results": fetch_google_signals(person, company)
            }
            return profile
        except Exception as e:
            logger.error(f"Agent 3 profiling failed for {person}: {e}")
            return {
                "name": person,
                "error": f"Agent 3 profiling failed: {str(e)}"
            }

    profiles = []
    with ThreadPoolExecutor(max_workers=min(8, len(people))) as executor:
        future_to_person = {executor.submit(build_profile, person): person for person in people}
        for future in as_completed(future_to_person):
            profiles.append(future.result())
    return profiles

def fetch_newsdata_signals(person: str, company: str) -> str:
    """
    Fetch recent news signals for a person at a company using NewsData.io.
    """
    if not NEWSDATA_API_KEY:
        logger.warning("NEWSDATA_API_KEY not set. Skipping news fetch.")
        return "NewsData.io API key not set."
    try:
        url = "https://newsdata.io/api/1/news"
        params = {
            "apikey": NEWSDATA_API_KEY,
            "q": f"{person} {company}",
            "language": "en",
            "category": "business",
            "page": 1
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        articles = data.get("results", [])[:3]
        if not articles:
            return "No recent news found."
        return "\n".join([f"- {a['title']} ({a.get('link', 'no link')})" for a in articles])
    except Exception as e:
        logger.warning(f"NewsData.io fetch failed for {person}: {e}")
        return f"NewsData.io fetch failed: {str(e)}"

def enrich_with_public_signals(person: str, company: str) -> str:
    """
    Use Groq to summarize public presence and professional background.
    """
    prompt = f"""
Search for public web results about {person} at {company}. Prioritize:
- LinkedIn profile summary
- Conference appearances
- Blog posts or authored content
- Career history

Summarize what you can learn about their public presence and professional background.
"""
    try:
        result = call_groq(prompt)
        return result.get("content", result).strip() if isinstance(result, dict) else str(result).strip()
    except Exception as e:
        logger.error(f"Groq enrichment failed for {person}: {e}")
        return f"Groq enrichment failed: {str(e)}"

def fetch_google_signals(person: str, company: str) -> str:
    """
    Fetch public web results for a person at a company using Google Custom Search.
    """
    if not SEARCH_API_KEY or not GOOGLE_CSE_ID:
        logger.warning("Google Search API key or CSE ID not set. Skipping Google fetch.")
        return "Google Search API key or CSE ID not set."
    try:
        query = f'"{person}" "{company}" site:linkedin.com OR site:crunchbase.com OR site:businesswire.com'
        params = {
            "key": SEARCH_API_KEY,
            "cx": GOOGLE_CSE_ID,
            "q": query,
            "num": max_results
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
        logger.warning(f"Google Search API fetch failed for {person}: {e}")
        return f"Google Search API fetch failed: {str(e)}"

def infer_role_focus(person: str, company: str) -> str:
    """
    Use Groq to infer a person's likely focus area based on job title and company.
    """
    prompt = f"""
Given the person's name \"{person}\" and the company \"{company}\", infer their likely focus area based on their job title.
Describe 2–3 business or technical priorities based on their likely job function and industry context.
"""
    try:
        result = call_groq(prompt)
        return result.get("content", result).strip() if isinstance(result, dict) else str(result).strip()
    except Exception as e:
        logger.error(f"Groq role focus inference failed for {person}: {e}")
        return f"Groq role focus inference failed: {str(e)}"

def check_filings_mention(person: str, company: str) -> str:
    """
    Use Groq to check if a person is mentioned in the last two 10-Q filings of a company.
    """
    prompt = f"""
Check the last two 10-Q from {company}. Was {person} mentioned?
If so, quote the sentence and summarize why.
"""
    try:
        result = call_groq(prompt)
        return result.get("content", result).strip() if isinstance(result, dict) else str(result).strip()
    except Exception as e:
        logger.error(f"Groq filings mention check failed for {person}: {e}")
        return f"Groq filings mention check failed: {str(e)}"

def infer_stack_from_job_posts(company: str) -> str:
    """
    Use Groq to infer likely tech stack from job postings for a company.
    """
    prompt = f"""
Based on recent job listings and analyst insight, what security or IT tools is {company} likely using?
What open positions does the company have in the area of focus for our meeting contact?
Mention 3–5 platform or vendor names relevant to modern enterprise IT.
"""
    try:
        result = call_groq(prompt)
        return result.get("content", result).strip() if isinstance(result, dict) else str(result).strip()
    except Exception as e:
        logger.error(f"Groq stack inference failed for {company}: {e}")
        return f"Groq stack inference failed: {str(e)}"

def estimate_tenure(person: str) -> str:
    """
    Use Groq to estimate a person's tenure and influence level.
    """
    prompt = f"""
Estimate how long \"{person}\" has been in their current role. Be realistic and plausible.
If you can infer influence level (e.g., keynote speaker, thought leader), include that too.
"""
    try:
        result = call_groq(prompt)
        return result.get("content", result).strip() if isinstance(result, dict) else str(result).strip()
    except Exception as e:
        logger.error(f"Groq tenure estimation failed for {person}: {e}")
        return f"Groq tenure estimation failed: {str(e)}"

def infer_risk_signals(person: str) -> str:
    """
    Use Groq to infer possible soft signals about a person's leadership style or risk profile.
    """
    prompt = f"""
What are possible soft signals about {person}'s leadership style or risk profile?
Examples:
- Recently joined → may be reshaping strategy
- Long tenured → resistant to change
- Public advocate → open to co-innovation
"""
    try:
        result = call_groq(prompt)
        return result.get("content", result).strip() if isinstance(result, dict) else str(result).strip()
    except Exception as e:
        logger.error(f"Groq risk signal inference failed for {person}: {e}")
        return f"Groq risk signal inference failed: {str(e)}"

def format_profiles_for_teams(profiles: List[Dict[str, Any]]) -> str:
    """
    Converts the list of Agent 3 profiles into Teams-friendly markdown.
    """
    blocks = []
    for p in profiles:
        if "error" in p:
            blocks.append(f"### ❌ **{p['name']}**\nError: {p['error']}")
            continue
        block = f"""
### 👤 **{p['name']}** — Executive Profile  
**Role Focus:**  
{p['role_focus']}

**Mention in SEC Filings:**  
{p['filing_reference']}

**Likely Tech Stack:**  
{p['likely_toolchain']}

**Estimated Tenure / Influence:**  
{p['estimated_tenure']}

**Leadership Style / Risk Profile:**  
{p['profile_signals']}

**Public Presence & Background:**  
{p['public_presence']}

**Public Web Presence:**  
{p['public_web_results']}

**Recent Mentions (NewsData.io):**  
{p['news_mentions']}
""".strip()
        blocks.append(block)
    return "\n\n---\n\n".join(blocks)
