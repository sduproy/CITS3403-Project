"""
AI itinerary generator backed by Google AI Studio's Gemma models.

Public API:

    plan = generate_itinerary(destination, arrive_time, leave_time)

returns a validated ``ItineraryPlan`` Pydantic model on success, or
raises ``GemmaError`` with a user-facing message on failure (missing
API key, network, malformed response, refusal, etc.). The route
layer flashes ``GemmaError.user_message`` and bounces the user back
to the homepage.

The structured output is enforced by passing the Pydantic schema as
``response_schema`` to the Gemma call — Gemma is then forced to return
JSON matching the schema, which we round-trip through
``ItineraryPlan.model_validate_json``. JSON serialisation for
persistence happens in routes.py via ``plan.model_dump_json()``; the
``Itinerary.content`` column stores the result.
"""

from __future__ import annotations

from datetime import datetime

from flask import current_app
from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel, Field, ValidationError


# ── Public schema ───────────────────────────────────────────────────────
# These models are also what gets serialised into Itinerary.content as
# JSON, and read back when trip_details.html renders the plan. Keep
# field names stable — changing them is a template-side breakage.


class Activity(BaseModel):
    time: str = Field(description="24-hour HH:MM start time, local to the destination.")
    title: str = Field(description="Short activity name.")
    description: str = Field(description="One or two sentences about what to do.")
    location: str = Field(description="Specific neighbourhood or place name.")
    duration_minutes: int = Field(description="Estimated duration in minutes.")


class Day(BaseModel):
    day_number: int = Field(description="1-indexed day of the trip.")
    date: str = Field(description="ISO date (YYYY-MM-DD) for the day.")
    title: str = Field(description="Short title for the day, e.g. 'Arrival & Shibuya'.")
    activities: list[Activity]


class ItineraryPlan(BaseModel):
    destination: str
    summary: str = Field(description="One or two sentences describing the trip's theme.")
    days: list[Day]


# ── Errors ──────────────────────────────────────────────────────────────


class GemmaError(Exception):
    """Anything that goes wrong while talking to Gemma.

    ``user_message`` is safe to flash to the end user; the underlying
    exception (if any) is the chained ``__cause__`` for logging.
    """

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


# ── Prompt ──────────────────────────────────────────────────────────────


_MODEL_NAME = "gemma-3-27b-it"
"""Largest open Gemma 3 model on AI Studio. Smaller variants
(gemma-3-12b-it, gemma-3-4b-it) are cheaper / faster but produce
noticeably worse structured output for multi-day plans."""


def _build_prompt(destination: str, arrive_time: datetime, leave_time: datetime) -> str:
    """The prompt we hand to Gemma. The schema is enforced separately by
    response_schema; this prose just describes the task and the rules
    we want the model to respect."""
    arrive_iso = arrive_time.strftime("%Y-%m-%d %H:%M")
    leave_iso = leave_time.strftime("%Y-%m-%d %H:%M")
    return (
        "You are a travel planner. Build a realistic day-by-day itinerary for "
        "the trip below.\n"
        "\n"
        f"Destination: {destination}\n"
        f"Arrival at the destination: {arrive_iso} (local time, the moment they land)\n"
        f"Departure from the destination: {leave_iso} (local time, the moment they leave)\n"
        "\n"
        "Rules:\n"
        "1. The first day's activities must START AFTER the arrival time. Do not "
        "schedule anything before the traveller has actually arrived.\n"
        "2. The last day's activities must END BEFORE the departure time. Leave "
        "enough buffer to reach the airport / station.\n"
        "3. Each day should have 4-6 activities including meals (breakfast, "
        "lunch, dinner) at sensible times.\n"
        "4. Use 24-hour HH:MM format for activity times.\n"
        "5. Activities should be in chronological order within each day, with "
        "realistic gaps for travel between locations.\n"
        "6. Be specific about locations — name actual neighbourhoods, districts, "
        "or venue names within the destination, not vague things like 'downtown'.\n"
        "7. day_number starts at 1 and increases by 1 per day.\n"
        "8. date is the ISO date for that day (YYYY-MM-DD).\n"
    )


# ── Public entry point ──────────────────────────────────────────────────


def generate_itinerary(
    destination: str,
    arrive_time: datetime,
    leave_time: datetime,
) -> ItineraryPlan:
    """Generate a structured itinerary by calling Gemma on Google AI Studio.

    Raises ``GemmaError`` on any failure mode. The caller (routes.py)
    is responsible for catching and flashing ``GemmaError.user_message``.
    """
    api_key = current_app.config.get("GOOGLE_API_KEY")
    if not api_key:
        raise GemmaError(
            "AI itinerary generation is not configured on this server. "
            "Set GOOGLE_API_KEY in the .env file and restart."
        )

    prompt = _build_prompt(destination, arrive_time, leave_time)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=_MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ItineraryPlan,
            ),
        )
    except APIError as e:
        # Network failure, rate limit, invalid key, model refusal, etc.
        raise GemmaError(
            "Couldn't reach the AI service. Please try again in a moment."
        ) from e
    except Exception as e:  # noqa: BLE001 — final safety net for unexpected SDK errors
        raise GemmaError(
            "Something went wrong while generating your itinerary. Please try again."
        ) from e

    raw_text = (response.text or "").strip()
    if not raw_text:
        raise GemmaError(
            "The AI returned an empty itinerary. Try rephrasing your destination or dates."
        )

    try:
        return ItineraryPlan.model_validate_json(raw_text)
    except ValidationError as e:
        # Gemma normally honours response_schema, but it can drift on edge
        # cases (e.g. very short trips). Treat as a transient error.
        raise GemmaError(
            "The AI returned an itinerary in an unexpected format. Please try again."
        ) from e
