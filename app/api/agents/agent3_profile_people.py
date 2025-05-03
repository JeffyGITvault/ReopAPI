import os
import requests
from app.api.groq_client import call_groq

NEWS_API_KEY = os.getenv("NEWSDATA_API_KEY")

def profile_people(people: list[str], company: str) -> list:
    """
    Agent 3: Comprehensive profiling using NewsData.io, Groq, and simulated signals.
    """
    if not people:
        return {"error": "No people provided for profiling."}

    profiles = []

    for person in people:
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
                "public_presence_Web": fetch_google_signals(person, company)

            }
            profiles.append(profile)
        except Exception as e:
            profiles.append({
                "name": person,
                "error": f"Agent 3 profiling failed: {str(e)}"
            })

    return profiles

def fetch_newsdata_signals(person: str, company: str) -> str:
    """
    Fetch recent news headlines via NewsData.io mentioning the person and company.
    """
    try:
        url = "https://newsdata.io/api/1/news"
        params = {
            "apikey": NEWS_API_KEY,
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
        return f"NewsData.io fetch failed: {str(e)}"

def enrich_with_public_signals(person: str, company: str) -> str:
    prompt = f"""
Search for public web results about {person} at {company}. Prioritize:
- LinkedIn profile summary
- Conference appearances
- Blog posts or authored content
- Career history

Summarize what you can learn about their public presence and professional background.
"""
    return call_groq(prompt).get("content", "").strip()

def fetch_google_signals(person: str, company: str) -> str:
    """
    Uses the Google Programmable Search API to fetch public web results for the person.
    Prioritizes domains like LinkedIn, Crunchbase, BusinessWire.
    """
    try:
        query = f'"{person}" "{company}" site:linkedin.com OR site:crunchbase.com OR site:businesswire.com'
        params = {
            "key": os.getenv("SEARCH_API_KEY"),
            "cx": os.getenv("GOOGLE_CSE_ID"),
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
        return f"Google Search API fetch failed: {str(e)}"
        
def infer_role_focus(person: str, company: str) -> str:
    prompt = f"""
Given the person's name \"{person}\" and the company \"{company}\", infer their likely focus area based on their job title.
Describe 2–3 business or technical priorities based on their likely job function and industry context.
"""
    return call_groq(prompt).get("content", "").strip()

def check_filings_mention(person: str, company: str) -> str:
    prompt = f"""
Check the last two 10-Q from {company}. Was {person} mentioned?
If so, quote the sentence and summarize why.
"""
    return call_groq(prompt).get("content", "").strip()

def infer_stack_from_job_posts(company: str) -> str:
    prompt = f"""
Based on recent job listings and analyst insight, what security or IT tools is {company} likely using?
what open positions does the comapny have in the area of focus for our meeting contact?
Mention 3–5 platform or vendor names relevant to modern enterprise IT.
"""
    return call_groq(prompt).get("content", "").strip()

def infer_risk_signals(person: str) -> str:
    prompt = f"""
What are possible soft signals about {person}'s leadership style or risk profile?
Examples:
- Recently joined → may be reshaping strategy
- Long tenured → resistant to change
- Public advocate → open to co-innovation
"""
    return call_groq(prompt).get("content", "").strip()

def format_profiles_for_teams(profiles: list) -> str:
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

**Leadership Style / Risk Profile:**  
{p['profile_signals']}

**Public Presence & Background:**  
{p['public_presence']}

**Public Web Presence:**  
{p['public_presence']}

**Recent Mentions (NewsData.io):**  
{p['news_mentions']}
""".strip()
        blocks.append(block)

    return "\n\n---\n\n".join(blocks)
