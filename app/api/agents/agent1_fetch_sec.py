# app/api/agents/agent1_fetch_sec.py

from app.api.SECAPI import fetch_quarterly_data  # Adjust based on your function names

def fetch_10q(company_name: str) -> dict:
    """
    Fetch latest 10-Q data for the company using SECAPI backend.
    """
    try:
        quarterly_data = fetch_quarterly_data(company_name)
        
        # You could post-process here if needed (filter only 10-Q)
        return quarterly_data

    except Exception as e:
        return {"error": f"Failed to fetch SEC data: {str(e)}"}
