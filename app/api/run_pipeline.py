# app/api/run_pipeline.py

from fastapi import APIRouter, HTTPException, Body
from typing import List
from pydantic import BaseModel
import asyncio
from app.api.agents.agent1_fetch_sec import fetch_10q
from app.api.agents.agent2_analyze_financials import analyze_financials
from app.api.agents.agent3_profile_people import profile_people
from app.api.agents.agent4_analyze_company import analyze_company

router = APIRouter()

class PipelineRequest(BaseModel):
    company: str
    people: List[str]
    meeting_context: str
    
@router.post("/run_pipeline")
async def run_pipeline(payload: PipelineRequest):
    company = payload.company
    people = payload.people
    meeting_context = payload.meeting_context
    # Input validation
    if not company or not isinstance(company, str) or not company.strip():
        raise HTTPException(status_code=400, detail="Missing or invalid 'company' field.")
    if not isinstance(people, list) or not all(isinstance(p, str) and p.strip() for p in people):
        raise HTTPException(status_code=400, detail="'people' must be a non-empty list of non-empty strings.")
    if not meeting_context or not isinstance(meeting_context, str) or not meeting_context.strip():
        raise HTTPException(status_code=400, detail="Missing or invalid 'meeting_context' field.")
    """
    Full multi-agent pipeline:
    Agent 1 -> SEC 10-Q Fetch (required)
    Agent 2 -> Financial Analysis (parallel)
    Agent 3 -> People Profiling (parallel)
    Agent 4 -> Analyze Company (parallel)
    """
    try:
        # === Agent 1: SEC 10-Q Fetch ===
        sec_data = fetch_10q(company)

        if "error" in sec_data:
            raise Exception(f"Agent 1 failed: {sec_data['error']}")

        # === Launch Agent 2, 3, and 4 concurrently ===
        tasks = [
            asyncio.to_thread(analyze_financials, sec_data),
            asyncio.to_thread(profile_people, people, company),
            asyncio.to_thread(analyze_company, company, meeting_context)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        financial_analysis, people_profiles, company_analysis = results

        # === Soft Failures Handling ===
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

        if isinstance(company_analysis, dict) and "error" in company_analysis:
            company_analysis = {
                "status": "Agent 4 (Market Analysis) failed",
                "error_details": company_analysis["error"]
            }

        # === Final Output Packaging ===
        final_output = {
            "company": company,
            "meeting_context": meeting_context,
            "sec_data": sec_data,
            "financial_analysis": financial_analysis,
            "people_profiles": people_profiles,
            "market_analysis": company_analysis
        }

        return final_output

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
