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

def profile_people(people: List[str], company: str) -> List[Dict[str, Any]]:
    """
    Agent 3: Comprehensive profiling using Google enrichment and Groq.
    Returns a list of profile dicts for each person.
    """
    if not people:
        return [{"error": "No people provided for profiling."}]

    def build_profile(person: str) -> Dict[str, Any]:
        try:
            profile = {
                "name": person,
                "news_mentions": fetch_google_signals(person, company),  # Use Google only
                "role_focus": infer_role_focus(person, company),
                "filing_reference": check_filings_mention(person, company),
                "likely_toolchain": infer_stack_from_job_posts(company),
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

def infer_role_focus(person: str, company: str) -> str:
    """
    Use Groq to infer a person's likely focus area based on job title and company.
    """
    prompt = f"""
Given the person's name \"{person}\" and the company \"{company}\", infer their likely focus area based on their job title.
Describe 2–3 business or technical priorities based on their likely job function and industry context.
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

def infer_stack_from_job_posts(company: str) -> str:
    """
    Search for the company's careers/jobs page, extract job titles/descriptions, and use Groq to infer likely tech stack.
    """
    if not SEARCH_API_KEY or not GOOGLE_CSE_ID:
        logger.warning("Google Search API key or CSE ID not set. Skipping Google fetch for jobs page.")
        return "Google Search API key or CSE ID not set."
    try:
        # 1. Search for the company's careers/jobs page
        query = f'{company} careers OR jobs site:{company}.com'
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
        # 2. Try to fetch and extract job titles/descriptions from the first result
        jobs_url = items[0]["link"]
        try:
            jobs_resp = requests.get(jobs_url, timeout=10)
            jobs_resp.raise_for_status()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(jobs_resp.text, "html.parser")
            # Try to extract job titles (look for <h2>, <h3>, <a>, or <li> with 'job' in text)
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
        # 3. Pass the job data to Groq for stack inference
        prompt = f"""
Given the following job postings for {company}, infer what security or IT tools, platforms, or vendors the company is likely using. Mention 3–5 relevant technologies, and summarize any open positions that stand out.\n\nJob Listings:\n{jobs_text}\n\nRespond in a concise, bullet-pointed format.
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
