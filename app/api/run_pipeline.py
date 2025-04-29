# app/api/run_pipeline.py

from fastapi import APIRouter, HTTPException
from app.api.agents.agent1_fetch_sec import fetch_10q
from app.api.agents.agent2_analyze_financials import analyze_financials
from app.api.agents.agent3_profile_people import profile_people
from app.api.agents.agent4_market_analysis import analyze_market

router = APIRouter()

@router.post("/run_pipeline")
async def run_pipeline(company: str, people: list[str], meeting_context: str):
    """
    Full multi-agent pipeline:
    Agent 1 -> SEC 10-Q Fetch,
    Agent 2 -> Financial Analysis,
    Agent 3 -> People Profiling (coming soon),
    Agent 4 -> Market Analysis (coming soon).
    """
    try:
        # === Agent 1: SEC 10-Q Fetch ===
        sec_data = fetch_10q(company)

        if "error" in sec_data:
            raise Exception(f"Agent 1 failed: {sec_data['error']}")

        # === Agent 2: Financial Analysis ===
        financial_analysis = analyze_financials(sec_data)

        # Soft fail if Agent 2 encounters an error
        if "error" in financial_analysis:
            financial_analysis = {
                "status": "Agent 2 (Financial Analysis) failed",
                "error_details": financial_analysis["error"]
            }

       # === Agent 3: People Profiling ===
        people_profiles = profile_people(people)

        # Soft fail if Agent 3 encounters an error
        if isinstance(people_profiles, dict) and "error" in people_profiles:
            people_profiles = {
                "status": "Agent 3 (People Profiling) failed",
                "error_details": people_profiles["error"]
            }
         
        # === Agent 4: MArket Analysis ===
        market_analysis = analyze_market(company, meeting_context)
        
        if "error" in market_analysis:
            market_analysis = {
                "status": "Agent 4 (Market Analysis) failed",
                "error_details": market_analysis["error"]
            }

        # === Package Final Output ===
        final_output = {
            "company": company,
            "meeting_context": meeting_context,
            "sec_data": sec_data,
            "financial_analysis": financial_analysis,
            "people_profiles": people_profiles,
            "market_analysis": market_analysis
        }

        return final_output

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
