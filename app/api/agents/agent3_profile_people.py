# app/api/agents/agent3_profile_people.py

import os
import requests
from app.api.groq_client import call_groq

def profile_people(people: list[str], company: str) -> list:
    """
    Agent 3: Enhanced profile builder using role, company, Groq inference, and multiple inferred signals.
    """
    if not people:
        return {"error": "No people provided for profiling."}

    profiles = []

    for person in people:
        try:
            # === Simulated Aggregation + Inference ===
            base_summary = infer_role_focus(person, company)
            filings_mention = check_filings_mention(person, company)
            toolchain = infer_stack_from_job_posts(company)
            estimated_tenure = estimate_tenure(person)
            risk_signals = infer_risk_signals(person)

            profiles.append({
                "name": person,
                "summary": base_summary,
                "filing_reference": filings_mention,
                "likely_toolchain": toolchain,
                "estimated_tenure": estimated_tenure,
                "profile_signals": risk_signals
            })

        except Exception as e:
            profiles.append({
                "name": person,
                "error": f"Agent 3 profiling failed: {str(e)}"
            })

    return profiles

def infer_role_focus(person: str, company: str) -> str:
    prompt = f"""
Given the person's name "{person}" and the company "{company}", infer their likely executive focus areas.
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
Estimate how long "{person}" has been in their current executive role. Be realistic and plausible.
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
