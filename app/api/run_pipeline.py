# app/api/run_pipeline.py

from fastapi import APIRouter, HTTPException
from app.api.agents.agent1_fetch_sec import fetch_10q
# Agent 2, Agent 3, Agent 4 will be imported later as they are built

router = APIRouter()

@router.post("/run_pipeline")
async def run_pipeline(company: str, people: list[str], meeting_context: str):
    """
    Full multi-agent pipeline:
    Agent 1 -> SEC 10-Q Fetch,
    Agent 2 -> Financial Analysis (coming soon),
    Agent 3 -> People Profiling (coming soon),
    Agent 4 -> Market Analysis (coming soon).
    """
    try:
        # === Agent 1: SEC 10-Q Fetch ===
        sec_data = fetch_10q(company)

        if "error" in sec_data:
            raise Exception(f"Agent 1 failed: {sec_data['error']}")

        # === Agent 2, 3, 4 === (stubs for now) ===
        financial_analysis = {"status": "Agent 2 not implemented yet"}
        people_profiles = {"status": "Agent 3 not implemented yet"}
        market_analysis = {"status": "Agent 4 not implemented yet"}

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
