# app/api/agents/agent3_profile_people.py

import requests
import os

# Eventually, store this safely — placeholder for now
BING_API_KEY = os.getenv("BING_API_KEY")
BING_SEARCH_URL = "https://api.bing.microsoft.com/v7.0/search"

def profile_people(people: list[str]) -> list:
    """
    Agent 3: Search for public LinkedIn profiles and basic summaries for a list of people.
    """
    if not people:
        return {"error": "No people provided for profiling."}

    profiles = []

    for person in people:
        try:
            profile = search_linkedin_profile(person)
            profiles.append(profile)
        except Exception as e:
            profiles.append({
                "name": person,
                "error": f"Failed to profile: {str(e)}"
            })

    return profiles

def search_linkedin_profile(name: str) -> dict:
    """
    Use Bing Search API to find public LinkedIn info about a person.
    """
    if not BING_API_KEY:
        raise Exception("BING_API_KEY environment variable not set.")

    headers = {"Ocp-Apim-Subscription-Key": BING_API_KEY}
    params = {
        "q": f"{name} site:linkedin.com",
        "count": 1
    }

    response = requests.get(BING_SEARCH_URL, headers=headers, params=params)
    response.raise_for_status()

    results = response.json()
    web_pages = results.get("webPages", {}).get("value", [])

    if not web_pages:
        return {
            "name": name,
            "profile_summary": "No LinkedIn profile found."
        }

    first_result = web_pages[0]
    title = first_result.get("name", "No title")
    snippet = first_result.get("snippet", "No snippet")
    url = first_result.get("url", "No URL")

    return {
        "name": name,
        "title": title,
        "profile_summary": snippet,
        "linkedin_url": url
    }
