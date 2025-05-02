# app/api/run_pipeline.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import asyncio

from app.api.agents.agent1_fetch_sec import fetch_10q
from app.api.agents.agent2_analyze_financials import analyze_financials
from app.api.agents.agent3_profile_people import profile_people
from app.api.agents.agent4_market_analysis import analyze_market

router = APIRouter()

class PipelineRequest(BaseModel):
    company: str
    people: List[str]
    meeting_context: str

@router.post("/run_pipeline")
async def run_pipeline(payload: PipelineRequest):
    """
    Full multi-agent pipeline:
    Agent 1 -> SEC 10-Q Fetch (required)
    Agent 2 -> Financial Analysis (parallel)
    Agent 3 -> People Profiling (parallel)
    Agent 4 -> Market Analysis (parallel)
    """
    try:
        # === Agent 1: SEC 10-Q Fetch ===
        sec_data = fetch_10q(payload.company)
        if "error" in sec_data:
            raise Exception(f"Agent 1 failed: {sec_data['error']}")

        # === Agents 2, 3, 4 in parallel ===
        tasks = [
            asyncio.to_thread(analyze_financials, sec_data),
            asyncio.to_thread(profile_people, payload.people),
            asyncio.to_thread(analyze_market, payload.company, payload.meeting_context)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        financial_analysis, people_profiles, market_analysis = results

        # === Soft Failure Wrappers ===
        if isinstance(financial_analysis, dict) and "error" in financial_analysis:
            financial_analysis = {
                "status": "Agent 2 (Financial Analysis) failed",
                "error_details": financial_analysis["error"]
            }

        if isinstance(people_profiles, dict) and "error" in people_profiles:
            people_profiles = {
                "status": "Agent 3 (People Profiling) failed",
                "error_details": people_profiles["error"]
            }

        if isinstance(market_analysis, dict) and "error" in market_analysis:
            market_analysis = {
                "status": "Agent 4 (Market Analysis) failed",
                "error_details": market_analysis["error"]
            }

        return {
            "company": payload.company,
            "meeting_context": payload.meeting_context,
            "sec_data": sec_data,
            "financial_analysis": financial_analysis,
            "people_profiles": people_profiles,
            "market_analysis": market_analysis
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
