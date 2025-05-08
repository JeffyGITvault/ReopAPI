# app/api/agents/agent3_profile_people.py

import os
import requests
import logging
from typing import List, Dict, Any
from app.api.groq_client import call_groq
from app.api.config import SEARCH_API_KEY, GOOGLE_CSE_ID
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

max_results = 5

def extract_business_unit_keywords(title: str) -> list:
    if not title:
        return []
    title = title.lower()
    keywords = []
    if "security" in title:
        keywords.append("security")
    if "cloud" in title:
        keywords.append("cloud")
    if "it" in title or "information technology" in title:
        keywords.append("IT")
    if "network" in title:
        keywords.append("network")
    if "infrastructure" in title:
        keywords.append("infrastructure")
    if "data" in title:
        keywords.append("data")
    # Add more as needed
    return keywords

def profile_people(people: List[str], company: str, titles: List[str] = None) -> List[Dict[str, Any]]:
    """
    Agent 3: Comprehensive profiling using Google enrichment and Groq.
    Returns a list of profile dicts for each person.
    """
    if not people:
        return [{"error": "No people provided for profiling."}]

    def build_profile(person: str, title: str = None) -> Dict[str, Any]:
        try:
            business_unit_keywords = extract_business_unit_keywords(title)
            profile = {
                "name": person,
                "title": title,  # Pass title if available
                "news_mentions": fetch_google_signals(person, company),
                "role_focus": infer_role_focus(person, company, title),
                "filing_reference": check_filings_mention(person, company),
                "likely_toolchain": infer_stack_from_job_posts(company, business_unit_keywords),
                "public_presence": enrich_with_public_signals(person, company),
                "public_web_results": fetch_google_signals(person, company),
                "signals": []  # Placeholder, can be filled with actual signals if available
            }
            return profile
        except Exception as e:
            logger.error(f"Agent 3 profiling failed for {person}: {e}")
            return {
                "name": person,
                "title": title,
                "error": f"Agent 3 profiling failed: {str(e)}",
                "signals": [f"Agent 3 profiling failed: {str(e)}"]
            }

    profiles = []
    titles = titles or [None] * len(people)
    with ThreadPoolExecutor(max_workers=min(8, len(people))) as executor:
        future_to_person = {executor.submit(build_profile, person, titles[i] if i < len(titles) else None): person for i, person in enumerate(people)}
        for future in as_completed(future_to_person):
            profiles.append(future.result())
    return profiles

def enrich_with_public_signals(person: str, company: str) -> str:
    """
    Use Groq to summarize public presence and professional background.
    """
    prompt = f"""
Search for public web results about {person} at {company}. Prioritize:
- LinkedIn profile summary
- Conference appearances
- Blog posts or authored content if found share source links with user
- Career history from LinkedIn

Summarize what you can learn about their public presence and professional background.
"""
    try:
        result = call_groq(prompt, max_tokens=32768)
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

def infer_role_focus(person: str, company: str, title: str = None) -> str:
    """
    Use Groq to analyze the likely impact on the client company and this person (by name and title) based on recent company news and general industry news. Avoid open-ended inference; ground the analysis in actual news and context.
    """
    title_str = f" ({title})" if title else ""
    prompt = f"""
Given the person's name "{person}"{title_str} at the company "{company}", analyze the likely impact of recent company news and general industry news on their role and priorities.

- Use only information that can be reasonably inferred from recent news about the company or the industry.
- If no relevant news is found, state that explicitly.
- Do not speculate beyond the available news context.
- Summarize 2–3 business or technical priorities for this person, grounded in the news context.
"""
    try:
        result = call_groq(prompt, max_tokens=32768)
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
        result = call_groq(prompt, max_tokens=32768)
        return result.get("content", result).strip() if isinstance(result, dict) else str(result).strip()
    except Exception as e:
        logger.error(f"Groq filings mention check failed for {person}: {e}")
        return f"Groq filings mention check failed: {str(e)}"

def infer_stack_from_job_posts(company: str, business_unit_keywords: list = None) -> str:
    """
    Search for the company's careers/jobs page, extract job titles/descriptions, and use Groq to infer likely tech stack.
    """
    if not SEARCH_API_KEY or not GOOGLE_CSE_ID:
        logger.warning("Google Search API key or CSE ID not set. Skipping Google fetch for jobs page.")
        return "Google Search API key or CSE ID not set."
    try:
        # Build query with business unit keywords
        keywords = " OR ".join(business_unit_keywords) if business_unit_keywords else ""
        query = f'{company} careers OR jobs {keywords} site:{company}.com'
        params = {
            "key": SEARCH_API_KEY,
            "cx": GOOGLE_CSE_ID,
            "q": query,
            "num": 3
        }
        response = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=10)
        response.raise_for_status()
        items = response.json().get("items", [])
        if not items:
            return "No careers page found."
        jobs_url = items[0]["link"]
        try:
            jobs_resp = requests.get(jobs_url, timeout=10)
            jobs_resp.raise_for_status()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(jobs_resp.text, "html.parser")
            jobs = []
            for tag in soup.find_all(["h2", "h3", "a", "li"]):
                text = tag.get_text(separator=" ", strip=True)
                if ("job" in text.lower() or "engineer" in text.lower() or "developer" in text.lower() or "analyst" in text.lower() or "manager" in text.lower()):
                    jobs.append(text)
                if len(jobs) >= 10:
                    break
            jobs_text = "\n".join(jobs) if jobs else soup.get_text(separator=" ", strip=True)[:2000]
        except Exception as e:
            logger.warning(f"Failed to fetch or parse jobs page: {e}")
            jobs_text = "Could not extract job listings."
        prompt = f"""
Given the following job postings for {company} (focus on roles related to {', '.join(business_unit_keywords) if business_unit_keywords else 'IT, Security, Cloud, Networking'}), infer what security or IT tools, platforms, or vendors the company is likely using. Mention 3–5 relevant technologies, and summarize any open positions that stand out.

Job Listings:
{jobs_text}

Respond in a concise, bullet-pointed format.
"""
        try:
            result = call_groq(prompt, max_tokens=32768)
            return result.get("content", result).strip() if isinstance(result, dict) else str(result).strip()
        except Exception as e:
            logger.error(f"Groq stack inference failed for {company}: {e}")
            return f"Groq stack inference failed: {str(e)}"
    except Exception as e:
        logger.error(f"Google Search API fetch for jobs page failed for {company}: {e}")
        return f"Google Search API fetch for jobs page failed: {str(e)}"

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

**Public Presence & Background:**  
{p['public_presence']}

**Public Web Presence:**  
{p['public_web_results']}

**Recent Mentions (NewsData.io):**  
{p['news_mentions']}
""".strip()
        blocks.append(block)
    return "\n\n---\n\n".join(blocks)
