import os
import json
import requests
from fastapi import APIRouter, Depends, HTTPException, Header, Body
from pydantic import BaseModel
from datetime import datetime
from typing import Any, Dict
from app.api.agents.analyze_private_company import analyze_private_company
from fastapi.middleware.cors import CORSMiddleware
import re

QUESTION_BANK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "customgpt_question_bank_v4_9_reconstructed_full.json")
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
LOG_PATH = os.path.join(LOGS_DIR, "question_bank.log")
ANALYTICS_PATH = os.path.join(LOGS_DIR, "question_bank_analytics.jsonl")

# Hybrid loader config
CUSTOMGPT_KB_URL = os.getenv("CUSTOMGPT_KB_URL", "https://api.customgpt.ai/knowledge/question_bank")
CUSTOMGPT_KB_TOKEN = os.getenv("CUSTOMGPT_KB_TOKEN", "")
USE_CUSTOMGPT_KB = os.getenv("USE_CUSTOMGPT_KB", "false").lower() == "true"

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

# Hybrid loader for question bank
def load_question_bank():
    if USE_CUSTOMGPT_KB:
        headers = {"Authorization": f"Bearer {CUSTOMGPT_KB_TOKEN}"} if CUSTOMGPT_KB_TOKEN else {}
        try:
            resp = requests.get(CUSTOMGPT_KB_URL, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            # Fallback to local file if API fails
            with open(QUESTION_BANK_PATH) as f:
                return json.load(f)
    else:
        with open(QUESTION_BANK_PATH) as f:
            return json.load(f)

def save_question_bank(data):
    if USE_CUSTOMGPT_KB:
        headers = {"Authorization": f"Bearer {CUSTOMGPT_KB_TOKEN}", "Content-Type": "application/json"} if CUSTOMGPT_KB_TOKEN else {"Content-Type": "application/json"}
        try:
            resp = requests.post(CUSTOMGPT_KB_URL, headers=headers, json=data, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as e:
            # Fallback: also save locally if RAG update fails
            with open(QUESTION_BANK_PATH, "w") as f:
                json.dump(data, f, indent=2)
            raise HTTPException(status_code=500, detail=f"Failed to update RAG KB: {e}")
    else:
        with open(QUESTION_BANK_PATH, "w") as f:
            json.dump(data, f, indent=2)
    return True

# --- Sync script: push local file to RAG KB ---
def sync_local_to_rag():
    """Push the local question bank file to the CustomGPT knowledge base."""
    if not CUSTOMGPT_KB_TOKEN:
        print("CUSTOMGPT_KB_TOKEN is not set.")
        return False
    with open(QUESTION_BANK_PATH) as f:
        data = json.load(f)
    headers = {"Authorization": f"Bearer {CUSTOMGPT_KB_TOKEN}", "Content-Type": "application/json"}
    try:
        resp = requests.post(CUSTOMGPT_KB_URL, headers=headers, json=data, timeout=10)
        resp.raise_for_status()
        print(f"Sync successful: {resp.status_code}")
        return True
    except Exception as e:
        print(f"Sync failed: {e}")
        return False

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
    data = load_question_bank()
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
    data = load_question_bank()
    for k, v in payload.update.items():
        data[k] = v
    data["version"] = data.get("version", 0) + 1
    save_question_bank(data)
    log_action(x_agent_id, "update", {"update": payload.update, "reason": payload.reason, "new_version": data["version"]})
    log_analytics(x_agent_id, "update_question_bank", {"update": payload.update, "reason": payload.reason, "new_version": data["version"]})
    return {"status": "success", "version": data["version"]}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "sync":
        sync_local_to_rag()
    else:
        print("Usage: python question_bank.py sync")

# Remove or comment out the following block, as 'app' is not defined here:
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# ) 