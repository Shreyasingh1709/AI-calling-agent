# ----------------------------
# Imports
# ----------------------------
import os
import json
import uuid
import re
import requests
import datetime
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv


# ----------------------------
# Initial Setup
# ----------------------------
load_dotenv()
 
app = FastAPI(title="AI Calling Campaign Engine")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Webhook URL from .env
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")

CAMPAIGN_FILE = "campaigns.json"


# ----------------------------
# Models
# ----------------------------

class GenerateScriptRequest(BaseModel):
    campaign_name: str
    campaign_purpose: str
    tone: str
    voice: str
    numbers: List[str]


class ApproveCampaignRequest(BaseModel):
    campaign_id: str


class CallStatusWebhook(BaseModel):
    campaign_id: str
    phone_number: str
    call_status: str
    duration: int


class SummaryRequest(BaseModel):
    campaign_id: str


# ----------------------------
# Utility Functions
# ----------------------------

def load_campaigns():
    if not os.path.exists(CAMPAIGN_FILE):
        with open(CAMPAIGN_FILE, "w") as f:
            json.dump([], f)

    with open(CAMPAIGN_FILE, "r") as f:
        return json.load(f)


def save_campaigns(data):
    with open(CAMPAIGN_FILE, "w") as f:
        json.dump(data, f, indent=4)


def clean_numbers(numbers):
    cleaned = []
    for n in numbers:
        n = n.replace(" ", "").replace("-", "")
        if re.match(r"^\+\d{10,15}$", n):
            cleaned.append(n)
    return cleaned


def call_openrouter(prompt):
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not configured")

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "mistralai/mixtral-8x7b-instruct",
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=20
        )

        if response.status_code != 200:
            raise Exception(response.text)

        result = response.json()
        return result["choices"][0]["message"]["content"]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------
# 1️⃣ Generate Script
# ----------------------------

@app.post("/generate-script")
def generate_script(data: GenerateScriptRequest):

    if not os.path.exists("knowledge_base.json"):
        raise HTTPException(status_code=500, detail="knowledge_base.json missing")

    if not os.path.exists("prompt.txt"):
        raise HTTPException(status_code=500, detail="prompt.txt missing")

    with open("knowledge_base.json") as f:
        knowledge = json.load(f)

    with open("prompt.txt") as f:
        template = f.read()

    cleaned_numbers = clean_numbers(data.numbers)

    if not cleaned_numbers:
        raise HTTPException(status_code=400, detail="No valid phone numbers provided")

    prompt = template.format(
        company_name=knowledge.get("company_name", ""),
        purpose=data.campaign_purpose,
        tone=data.tone,
        faq=json.dumps(knowledge.get("faq", {}), indent=2),
        user_message=data.campaign_purpose
    )

    script = call_openrouter(prompt)

    campaign_id = str(uuid.uuid4())

    campaign_record = {
        "campaign_id": campaign_id,
        "campaign_name": data.campaign_name,
        "purpose": data.campaign_purpose,
        "tone": data.tone,
        "voice": data.voice,
        "numbers": cleaned_numbers,
        "script": script,
        "status": "draft",
        "created_at": str(datetime.datetime.utcnow()),
        "call_logs": []
    }

    campaigns = load_campaigns()
    campaigns.append(campaign_record)
    save_campaigns(campaigns)

    return {
        "campaign_id": campaign_id,
        "script": script,
        "cleaned_numbers": cleaned_numbers
    }


# ----------------------------
# 2️⃣ Approve Campaign (Dummy Webhook for Testing)
# ----------------------------

@app.post("/approve-campaign")
def approve_campaign(data: ApproveCampaignRequest):

    campaigns = load_campaigns()

    campaign = next(
        (c for c in campaigns if c["campaign_id"] == data.campaign_id),
        None
    )

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign["status"] == "approved":
        return {"message": "Campaign already approved"}

    if not campaign["numbers"]:
        raise HTTPException(status_code=400, detail="No valid phone numbers to call")

    payload = {
        "campaign_id": campaign["campaign_id"],
        "campaign_name": campaign["campaign_name"],
        "numbers": campaign["numbers"],
        "script": campaign["script"],
        "voice": campaign["voice"]
    }

    try:
        response = requests.post(
            MAKE_WEBHOOK_URL,
            json=payload,
            timeout=10
        )

        # We allow 200–299 as success
        if not (200 <= response.status_code < 300):
            raise HTTPException(
                status_code=500,
                detail=f"Webhook failed: {response.text}"
            )

    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail=f"Automation trigger failed: {str(e)}"
        )

    campaign["status"] = "approved"
    save_campaigns(campaigns)

    return {
        "message": "Campaign successfully sent to automation layer (dummy)",
        "campaign_id": campaign["campaign_id"]
    }


# ----------------------------
# 3️⃣ Webhook (Simulated Call Status)
# ----------------------------

@app.post("/call-status-webhook")
def call_status_webhook(data: CallStatusWebhook):

    campaigns = load_campaigns()

    campaign = next(
        (c for c in campaigns if c["campaign_id"] == data.campaign_id),
        None
    )

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign["call_logs"].append({
        "phone_number": data.phone_number,
        "status": data.call_status,
        "duration": data.duration,
        "timestamp": str(datetime.datetime.utcnow())
    })

    save_campaigns(campaigns)

    return {"message": "Call log updated successfully"}


# ----------------------------
# 4️⃣ Generate Campaign Summary
# ----------------------------

@app.post("/generate-summary")
def generate_summary(data: SummaryRequest):

    campaigns = load_campaigns()

    campaign = next(
        (c for c in campaigns if c["campaign_id"] == data.campaign_id),
        None
    )

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    total_calls = len(campaign["call_logs"])

    summary_prompt = f"""
    Campaign Name: {campaign['campaign_name']}
    Purpose: {campaign['purpose']}
    Total Calls Completed: {total_calls}

    Call Logs:
    {json.dumps(campaign['call_logs'], indent=2)}

    Generate:
    - Performance summary
    - Conversion insight
    - Suggested next action
    """

    summary = call_openrouter(summary_prompt)

    return {"campaign_summary": summary}