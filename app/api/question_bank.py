import os
import json
from fastapi import APIRouter, Depends, HTTPException, Header, Body
from pydantic import BaseModel
from datetime import datetime
from typing import Any, Dict

QUESTION_BANK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "customgpt_question_bank_v4_9_reconstructed_full.json")
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
LOG_PATH = os.path.join(LOGS_DIR, "question_bank.log")
ANALYTICS_PATH = os.path.join(LOGS_DIR, "question_bank_analytics.jsonl")

AGENT_PERMISSIONS = {
    "agent3": {"read": True, "write": False},
    "agent4": {"read": True, "write": True},
}

router = APIRouter()

class QuestionBankUpdate(BaseModel):
    update: Dict[str, Any]
    reason: str

# Ensure logs directory exists
def ensure_logs_dir():
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)

# Access control dependency
def get_agent_permissions(x_agent_id: str = Header(...)):
    perms = AGENT_PERMISSIONS.get(x_agent_id)
    if not perms:
        raise HTTPException(status_code=403, detail="Invalid agent ID")
    return perms

def log_action(agent, action, details):
    ensure_logs_dir()
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "agent": agent,
            "action": action,
            "details": details
        }) + "\n")

def log_analytics(agent, event, details):
    ensure_logs_dir()
    with open(ANALYTICS_PATH, "a") as f:
        f.write(json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "agent": agent,
            "event": event,
            "details": details
        }) + "\n")

@router.get("/question_bank")
def get_question_bank(perms=Depends(get_agent_permissions), x_agent_id: str = Header(...)):
    if not perms["read"]:
        raise HTTPException(status_code=403, detail="Read access denied")
    with open(QUESTION_BANK_PATH) as f:
        data = json.load(f)
    log_action(x_agent_id, "read", {})
    log_analytics(x_agent_id, "read_question_bank", {})
    return data

@router.post("/question_bank")
def update_question_bank(
    payload: QuestionBankUpdate = Body(...),
    perms=Depends(get_agent_permissions),
    x_agent_id: str = Header(...)
):
    if not perms["write"]:
        raise HTTPException(status_code=403, detail="Write access denied")
    # Load current data
    with open(QUESTION_BANK_PATH) as f:
        data = json.load(f)
    # Apply update (for demo, just merge top-level keys)
    for k, v in payload.update.items():
        data[k] = v
    # Versioning
    data["version"] = data.get("version", 0) + 1
    # Save new version
    with open(QUESTION_BANK_PATH, "w") as f:
        json.dump(data, f, indent=2)
    # Optionally, backup previous version (not implemented here)
    log_action(x_agent_id, "update", {"update": payload.update, "reason": payload.reason, "new_version": data["version"]})
    log_analytics(x_agent_id, "update_question_bank", {"update": payload.update, "reason": payload.reason, "new_version": data["version"]})
    return {"status": "success", "version": data["version"]} 