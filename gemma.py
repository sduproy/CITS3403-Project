"""
AI itinerary generator backed by Google AI Studio's Gemma models.

Public API:

    plan = generate_itinerary(destination, arrive_time, leave_time)

returns a validated ``ItineraryPlan`` Pydantic model on success, or
raises ``GemmaError`` with a user-facing message on failure (missing
API key, network, malformed response, refusal, etc.). The route
layer flashes ``GemmaError.user_message`` and bounces the user back
to the homepage.

Why we don't use response_schema: AI Studio's structured-output mode
(``response_mime_type="application/json"`` + ``response_schema=...``)
is a Gemini-only feature — Gemma rejects it with
``JSON mode is not enabled for models/gemma-3-27b-it``. So we go the
JSON-in-prompt route instead: the prompt includes the JSON schema
inline, asks for "ONLY the JSON object", and the response is then
stripped of Gemma's habitual ```json ... ``` markdown fences before
being handed to ``ItineraryPlan.model_validate_json``. This is less
deterministic than response_schema but it's the only path that works
for Gemma today.

JSON serialisation for persistence happens in routes.py via
``plan.model_dump_json()``; the ``Itinerary.content`` column stores
the result.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from flask import current_app
from google import genai
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


_MODEL_NAME = "gemini-3.1-flash-lite"
"""Gemma 4 instruction-tuned model on Google AI Studio. Gemma 3 (27b
and below) was throttled with tighter free-tier rate limits after
Gemma 4 launched, so the bigger Gemma 4 variant is actually faster
end-to-end for our use case once you account for retries on
rate-limited Gemma 3 calls."""


_JSON_SCHEMA_HINT = """\
{
  "destination": "<destination name>",
  "summary": "<1-2 sentence overview of the trip's theme>",
  "days": [
    {
      "day_number": <1, 2, ...>,
      "date": "<YYYY-MM-DD>",
      "title": "<brief title for the day, e.g. 'Arrival & Shibuya'>",
      "activities": [
        {
          "time": "<HH:MM 24-hour>",
          "title": "<short activity name>",
          "description": "<one or two sentences>",
          "location": "<specific neighbourhood or venue>",
          "duration_minutes": <integer>
        }
      ]
    }
  ]
}"""


def _build_prompt(destination: str, arrive_time: datetime, leave_time: datetime) -> str:
    """Prompt that asks Gemma for a JSON itinerary. The schema is
    embedded inline because Gemma doesn't honour response_schema; the
    response will still need code-fence stripping (see _extract_json)
    because Gemma reliably wraps its JSON output in ```json ... ```.
    """
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
        "\n"
        "Respond with ONLY a single JSON object matching this exact shape "
        "(replace placeholders, keep all field names):\n"
        f"{_JSON_SCHEMA_HINT}\n"
    )


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def _extract_json(raw: str) -> str:
    """Strip the markdown code fences Gemma always adds around JSON.

    Falls back to a substring-from-first-{-to-last-} extraction if the
    fence pattern doesn't match, in case Gemma decides to add prose
    around the JSON on a particular run.
    """
    raw = raw.strip()
    fenced = _CODE_FENCE_RE.match(raw)
    if fenced:
        return fenced.group(1).strip()
    # Fallback: locate the outermost JSON object braces.
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1]
    return raw


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
        # No response_schema / response_mime_type — Gemma rejects those.
        # The schema lives inside the prompt and we parse the response.
        response = client.models.generate_content(
            model=_MODEL_NAME,
            contents=prompt,
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

    json_text = _extract_json(raw_text)
    try:
        return ItineraryPlan.model_validate_json(json_text)
    except (ValidationError, json.JSONDecodeError) as e:
        # Gemma occasionally drifts on the schema (extra fields, missing
        # fields, wrong types) or returns truncated JSON. Treat as a
        # transient error — the user can retry.
        raise GemmaError(
            "The AI returned an itinerary in an unexpected format. Please try again."
        ) from e
