# ruff: noqa
# Copyright 2026 Google LLC

import os
import re
import json
import logging
import datetime
import sys
from typing import AsyncGenerator, Any
from pydantic import BaseModel, Field

from google.adk.workflow import Workflow, node
from google.adk.agents import LlmAgent
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.genai import types

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .config import config

logging.basicConfig(level=logging.INFO)

# --- Pydantic Schemas ---

class SymptomReport(BaseModel):
    specialty: str = Field(description="The medical specialty required for the symptoms (e.g. dermatology, cardiology, ophthalmology, urgent_care, emergency).")
    severity: str = Field(description="Severity classification: 'RED' (emergency), 'YELLOW' (urgent, needs clinic visit), or 'GREEN' (routine, home care/general doctor).")
    notes: str = Field(description="Educational summary of potential causes and triage guidance. Avoid diagnosing or prescribing.")

class ProviderInfo(BaseModel):
    name: str = Field(description="Name of the hospital or clinic.")
    address: str = Field(description="Physical address of the provider.")
    distance: str = Field(description="Distance from the user's ZIP code.")
    wait_time_minutes: int = Field(description="Current waiting time in minutes.")
    reviews_summary: str = Field(description="Summary of patient reviews and sentiment.")

class HospitalRecommendations(BaseModel):
    recommended_providers: list[ProviderInfo] = Field(description="List of matching medical providers in the area.")

# --- MCP Toolset Initialization ---

mcp_server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "mcp_server.py"))

mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[mcp_server_path],
        )
    )
)

# --- Specialized LLM Agents ---

symptom_analyzer = LlmAgent(
    name="symptom_analyzer",
    model=config.model,
    instruction="""You are a medical triage specialist.
Analyze the user's described symptoms and any visual descriptions.
Classify the required medical specialty and the severity level:
- RED: Emergency (chest pain, severe breathing difficulty, sudden weakness, severe bleeding, etc.)
- YELLOW: Urgent (cuts needing stitches, mild infections, high fever, rashes with pain, etc.)
- GREEN: Routine (minor cold, dry rash, general health questions, etc.)

Provide educational guidance only. Never diagnose a specific disease or prescribe any treatments.

CRITICAL: You must return ONLY a valid JSON object matching the SymptomReport schema. Do NOT include any markdown code blocks, conversational introductions, greetings, or pleasantries.
""",
    tools=[mcp_toolset],  # Wired into 2 agents (symptom_analyzer & provider_locator)
    output_schema=SymptomReport,
    output_key="symptom_report"
)

provider_locator = LlmAgent(
    name="provider_locator",
    model=config.model,
    instruction="""You are a healthcare provider matchmaking coordinator.
Your task is to find the best local hospitals or clinics for the user.
1. Extract the required specialty and the user's ZIP code from the input message.
2. Query the MCP tools (using search_providers) to find matching providers in that ZIP code.
3. Query the wait times (get_wait_times) and reviews (get_provider_reviews) for the returned providers.
4. Compile the list of recommendations, including address, distance, live wait times, and a summary of reviews.

CRITICAL: You must return ONLY a valid JSON object matching the HospitalRecommendations schema. Do NOT include any markdown code blocks, conversational text, greetings, explanations, or pleasantries outside of the JSON.
""",
    tools=[mcp_toolset],
    output_schema=HospitalRecommendations,
    output_key="hospital_recommendations"
)

# --- Workflow Graph Nodes ---

def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    text = ""
    if node_input and node_input.parts:
        text = " ".join([p.text for p in node_input.parts if p.text])

    # 1. PII Scrubbing
    scrubbed_text = text
    # SSN
    scrubbed_text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN REDACTED]", scrubbed_text)
    # Phone
    scrubbed_text = re.sub(r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b", "[PHONE REDACTED]", scrubbed_text)
    # Email
    scrubbed_text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL REDACTED]", scrubbed_text)

    # 2. Prompt Injection Detection
    injection_keywords = ["ignore previous", "system prompt", "override instructions", "you are now a", "translate the above"]
    detected_injection = False
    for kw in injection_keywords:
        if kw in scrubbed_text.lower():
            detected_injection = True
            break

    # 3. Write structured JSON audit log
    audit_log = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "session_id": ctx.session.id,
        "input_length": len(text),
        "pii_redacted": scrubbed_text != text,
        "injection_detected": detected_injection,
        "severity": "INFO" if not detected_injection else "CRITICAL"
    }
    logging.info(f"AUDIT LOG: {json.dumps(audit_log)}")

    if detected_injection:
        return Event(
            output="Security Violation: Possible prompt injection detected.",
            route="violation"
        )

    # Look for ZIP and consent in the text
    consent_given = "consent" in scrubbed_text.lower() or "agree" in scrubbed_text.lower()
    zipcode = ""
    zip_match = re.search(r"\b\d{5}\b", scrubbed_text)
    if zip_match:
        zipcode = zip_match.group(0)

    # Store query and initial flags
    return Event(
        output=scrubbed_text,
        route="clean",
        state={
            "user_query": scrubbed_text,
            "consent_given": consent_given or ctx.state.get("consent_given", False),
            "zipcode": zipcode or ctx.state.get("zipcode", "")
        }
    )

@node(rerun_on_resume=True)
async def hitl_consent_gate(ctx: Context, node_input: dict) -> AsyncGenerator[Event, None]:
    # node_input is SymptomReport (dict) from symptom_analyzer
    severity = node_input.get("severity", "GREEN").upper()
    specialty = node_input.get("specialty", "")
    notes = node_input.get("notes", "")

    # Save to state
    ctx.state["symptom_specialty"] = specialty
    ctx.state["symptom_severity"] = severity
    ctx.state["symptom_notes"] = notes

    # 1. Emergency RED Severity Check
    if severity == "RED":
        yield Event(
            output=f"🚨 EMERGENCY ALERT: Your symptoms suggest a potentially life-threatening condition ({specialty}). Please call 911 or go to the nearest Emergency Room immediately. Do not wait for clinic recommendations.\n\nTriage Notes: {notes}",
            route="halt"
        )
        return

    # 2. Check for consent and ZIP code
    consent_given = ctx.state.get("consent_given", False)
    zipcode = ctx.state.get("zipcode", "")

    if not consent_given or not zipcode:
        if not ctx.resume_inputs or "user_consent" not in ctx.resume_inputs:
            yield RequestInput(
                interrupt_id="user_consent",
                message=(
                    f"Triage complete. Required specialty: {specialty} (Severity: {severity}).\n"
                    f"To proceed with hospital matchmaking, please confirm your ZIP code and provide HIPAA consent "
                    f"by responding with: 'I consent for ZIP <your-zip-code>' (e.g. 'I consent for ZIP 90210')."
                )
            )
            return

        # Resume execution
        user_response = ctx.resume_inputs["user_consent"]
        zip_match = re.search(r"\b\d{5}\b", user_response)
        consent_match = "consent" in user_response.lower() or "agree" in user_response.lower()

        if consent_match and zip_match:
            zipcode = zip_match.group(0)
            yield Event(
                output="Consent verified.",
                route="approved",
                state={"consent_given": True, "zipcode": zipcode}
            )
        else:
            yield Event(
                output="HIPAA consent or valid ZIP code was not provided. Matchmaking aborted.",
                route="halt",
                state={"consent_given": False}
            )
        return

    # If we already have consent and ZIP
    yield Event(
        output=f"Consent verified for ZIP {zipcode}.",
        route="approved"
    )


def prepare_locator_input(ctx: Context, node_input: Any) -> str:
    specialty = ctx.state.get("symptom_specialty", "general")
    severity = ctx.state.get("symptom_severity", "GREEN")
    zipcode = ctx.state.get("zipcode", "")
    notes = ctx.state.get("symptom_notes", "")
    return (
        f"Search for providers. Specialty required: {specialty}. "
        f"Severity: {severity}. "
        f"ZIP Code: {zipcode}. "
        f"Triage Notes: {notes}."
    )


def final_output(ctx: Context, node_input: Any) -> Event:
    output_text = ""
    rec_list = None

    # Handle Pydantic model or dict input
    if hasattr(node_input, "recommended_providers"):
        rec_list = node_input.recommended_providers
    elif isinstance(node_input, dict) and "recommended_providers" in node_input:
        rec_list = node_input["recommended_providers"]

    if rec_list:
        output_text = "### 🏥 Recommended Healthcare Providers\n\n"
        for rec in rec_list:
            # Safely get properties from either dict or Pydantic object
            def get_val(obj, key, default=""):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            name = get_val(rec, "name")
            address = get_val(rec, "address")
            distance = get_val(rec, "distance")
            wait_time = get_val(rec, "wait_time_minutes", 0)
            reviews = get_val(rec, "reviews_summary")

            output_text += (
                f"**{name}**\n"
                f"- 📍 Address: {address} (approx. {distance} away)\n"
                f"- ⏱ ER/Clinic Wait Time: **{wait_time} mins**\n"
                f"- ⭐ Patient Review Summary: {reviews}\n\n"
            )
        output_text += "\n*Note: This recommendations list is generated based on your described symptoms and specialty requirement. Please contact the clinic directly to verify insurance and current capacity.*"
    else:
        output_text = str(node_input)

    return Event(
        output=output_text,
        content=types.Content(
            role='model',
            parts=[types.Part.from_text(text=output_text)]
        )
    )


def security_alert(node_input: str) -> Event:
    output_text = f"🚨 SECURITY BLOCK: {node_input}"
    return Event(
        output=output_text,
        content=types.Content(
            role='model',
            parts=[types.Part.from_text(text=output_text)]
        )
    )


# --- Workflow Graph Setup ---

root_agent = Workflow(
    name="visual_triage_workflow",
    edges=[
        ('START', security_checkpoint),
        (security_checkpoint, {"clean": symptom_analyzer, "violation": security_alert}),
        (symptom_analyzer, hitl_consent_gate),
        (hitl_consent_gate, {"approved": prepare_locator_input, "halt": final_output}),
        (prepare_locator_input, provider_locator),
        (provider_locator, final_output),
        (security_alert, final_output),
    ],
    description="Orchestrates symptom analysis, HIPAA consent, local provider search, and security controls.",
)

# --- App Definition ---

app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True)
)
