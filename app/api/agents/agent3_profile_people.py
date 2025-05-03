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
                "profile_signals": infer_risk_signals(person)
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

def infer_role_focus(person: str, company: str) -> str:
    prompt = f"""
Given the person's name \"{person}\" and the company \"{company}\", infer their likely executive focus areas.
Assume this person holds a role like CIO, CISO, CMO, or COO.
Describe 2–3 business or technical priorities based on their likely job function and industry context.
"""
    return call_groq(prompt)["choices"][0]["message"]["content"].strip()

def check_filings_mention(person: str, company: str) -> str:
    prompt = f"""
Check the last two 10-Q or 10-K filings from {company}. Was {person} mentioned?
If so, quote the sentence and summarize why.
"""
    return call_groq(prompt)["choices"][0]["message"]["content"].strip()

def infer_stack_from_job_posts(company: str) -> str:
    prompt = f"""
Based on recent job listings and analyst insight, what security or IT tools is {company} likely using?
Mention 3–5 platform or vendor names relevant to modern enterprise IT.
"""
    return call_groq(prompt)["choices"][0]["message"]["content"].strip()

def estimate_tenure(person: str) -> str:
    prompt = f"""
Estimate how long \"{person}\" has been in their current executive role. Be realistic and plausible.
If you can infer influence level (e.g., keynote speaker, thought leader), include that too.
"""
    return call_groq(prompt)["choices"][0]["message"]["content"].strip()

def infer_risk_signals(person: str) -> str:
    prompt = f"""
What are possible soft signals about {person}'s leadership style or risk profile?
Examples:
- Recently joined → may be reshaping strategy
- Long tenured → resistant to change
- Public advocate → open to co-innovation
"""
    return call_groq(prompt)["choices"][0]["message"]["content"].strip()
