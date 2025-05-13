# app/api/run_pipeline.py

from fastapi import APIRouter, HTTPException, Body
from typing import List
from pydantic import BaseModel
import asyncio
from app.api.agents.agent1_fetch_sec import fetch_10q
from app.api.agents.agent2_analyze_financials import analyze_financials
from app.api.agents.agent3_profile_people import profile_people
from app.api.agents.agent4_analyze_company import analyze_company, build_market_prompt
from app.api.memory_schema import Agent2Financials, Agent3Profile, Agent4RiskMap
from app.api.prompt_builder import build_agent_1_prompt, format_table
import logging
import openai
import os
from app.api.agents.analyze_private_company import analyze_private_company

router = APIRouter()

class PipelineRequest(BaseModel):
    company: str
    people: List[str]
    meeting_context: str
    additional_context: dict = {}
    titles: List[str] = []  # Optional: allow user to pass titles
    
@router.post("/run_pipeline")
async def run_pipeline(payload: PipelineRequest):
    # Log if OPENAI_API_KEY is present
    logger = logging.getLogger("run_pipeline")
    logger.info(f"OPENAI_API_KEY is present: {'OPENAI_API_KEY' in os.environ}")
    company = payload.company
    people = payload.people
    meeting_context = payload.meeting_context
    additional_context = payload.additional_context or {}
    titles = payload.titles if hasattr(payload, 'titles') else [None] * len(people)
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
    Agent 5 -> Analyze Private Company (parallel)
    """
    try:
        # === Agent 1: SEC 10-Q Fetch ===
        sec_data = fetch_10q(company)
        is_public = bool(sec_data.get("filings")) and not sec_data.get("error")
        private_company_analysis = None
        if is_public:
            # Extract the extracted_sections from the most recent filing
            filings = sec_data.get("filings", [])
            if filings and filings[0].get("extracted_sections"):
                extracted_sections = filings[0]["extracted_sections"]
            else:
                extracted_sections = {}
            # === Launch Agent 2, 3, and 4 concurrently ===
            tasks = [
                asyncio.to_thread(analyze_financials, extracted_sections, additional_context),
                asyncio.to_thread(profile_people, people, company, titles),
                # Agent 4 will be called after Agent 2 and 3 finish, to allow dynamic contexting
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            financial_analysis, people_profiles = results
            # Prepare Agent 2 and 3 context for Agent 4
            agent2_summary = None
            agent3_profile = None
            try:
                agent2_summary = financial_analysis.get("financial_summary") if isinstance(financial_analysis, dict) else None
            except Exception:
                agent2_summary = None
            try:
                agent3_profile = people_profiles[0] if isinstance(people_profiles, list) and people_profiles else people_profiles
            except Exception:
                agent3_profile = None
            # Now run Agent 4 with dynamic context
            company_analysis = await asyncio.to_thread(analyze_company, company, meeting_context, agent2_summary, agent3_profile)
        else:
            # Private company workflow
            financial_analysis = {"error": "No SEC filings found. Company appears to be private."}
            people_profiles = await asyncio.to_thread(profile_people, people, company, titles)
            company_analysis = await asyncio.to_thread(analyze_company, company, meeting_context)
            private_company_analysis = await asyncio.to_thread(analyze_private_company, company, meeting_context, additional_context)
        # === Robust error handling for agent outputs ===
        agent2 = agent3 = agent4 = None
        agent2_error = agent3_error = agent4_error = None
        try:
            agent2 = Agent2Financials(**financial_analysis) if isinstance(financial_analysis, dict) else Agent2Financials.model_validate(financial_analysis)
        except Exception as e:
            agent2_error = f"Agent 2 output invalid: {e}"
            logger.error(agent2_error)
        try:
            profile = people_profiles[0] if isinstance(people_profiles, list) and people_profiles else people_profiles
            agent3 = Agent3Profile(
                name=profile.get("name"),
                title=profile.get("title"),
                signals=profile.get("signals", []),
                engagement_style=profile.get("engagement_style")
            ) if isinstance(profile, dict) else Agent3Profile.model_validate(profile)
        except Exception as e:
            agent3_error = f"Agent 3 output invalid: {e}"
            logger.error(agent3_error)
        try:
            agent4 = Agent4RiskMap(**company_analysis) if isinstance(company_analysis, dict) else Agent4RiskMap.model_validate(company_analysis)
        except Exception as e:
            agent4_error = f"Agent 4 output invalid: {e}"
            logger.error(agent4_error)
            # Ensure all required fields are present in fallback
            agent4 = Agent4RiskMap(
                threats=[agent4_error or "Unavailable"],
                opportunities=[],
                competitive_landscape=[],
                macroeconomic_factors=[],
                questions_to_ask=[]
            )
        # === Build meta-prompt (even if some agents failed) ===
        meta_prompt = build_agent_1_prompt(
            agent2 if agent2 else Agent2Financials(
                financial_summary=agent2_error or "Unavailable", key_metrics_table={}, recent_events_summary="", questions_to_ask=[], suggested_graph=None),
            agent3 if agent3 else Agent3Profile(
                name=people[0] if people else "Unknown", title=None, signals=[agent3_error or "Unavailable"], engagement_style=None),
            agent4 if agent4 else Agent4RiskMap(
                threats=[agent4_error or "Unavailable"], opportunities=[], competitive_landscape=[], macroeconomic_factors=[], questions_to_ask=[]),
            additional_context=additional_context,
            is_public=is_public,
            private_company_analysis=private_company_analysis,
            enforce_title=True
        )
        logger.info(f"Meta-prompt for synthesis:\n{meta_prompt}")
        # === Synthesis LLM call (OpenAI GPT-4-turbo) ===
        try:
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": "You are a world-class executive intelligence summarizer."},
                    {"role": "user", "content": meta_prompt}
                ],
                max_tokens=8192,
                temperature=0.4
            )
            executive_briefing = response.choices[0].message.content
            logger.info(f"Synthesis LLM result: {executive_briefing[:500]}...")
        except Exception as e:
            logger.error(f"Synthesis LLM call failed: {e}")
            executive_briefing = f"[SYNTHESIS LLM ERROR] {e}\n\n{meta_prompt}"
        # === Final Output Packaging ===
        final_output = {
            "company": company,
            "meeting_context": meeting_context,
            "is_public": is_public,
            "sec_data": sec_data,
            "financial_analysis": financial_analysis,
            "people_profiles": people_profiles,
            "market_analysis": company_analysis,
            "private_company_analysis": private_company_analysis,
            "executive_briefing": executive_briefing
        }
        return final_output
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
