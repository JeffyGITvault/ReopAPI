from typing import List, Dict, Optional
from pydantic import BaseModel

class Agent2Financials(BaseModel):
    financial_summary: str
    key_metrics_table: Dict[str, List[str]]
    recent_events_summary: str
    suggested_graph: Optional[str] = None
    questions_to_ask: List[str]

class Agent3Profile(BaseModel):
    name: str
    title: Optional[str] = None
    signals: List[str]
    engagement_style: Optional[str] = None

class Agent4RiskMap(BaseModel):
    threats: List[str]
    opportunities: List[str]
    competitive_landscape: List[Dict[str, str]]
    macroeconomic_factors: List[str]
    questions_to_ask: List[str] 