import json
import re
import logging
import time
import os
from dotenv import load_dotenv
from typing import Optional
import itertools

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MAX_TOKENS = 5000

SAFETY_DISCLAIMER = (
    "This is not a medical diagnosis. "
    "Please consult a healthcare professional if possible."
)

EMERGENCY_KEYWORDS = [
    "can't breathe", "cannot breathe", "difficulty breathing",
    "chest pain", "heart attack",
    "heavy bleeding", "bleeding heavily", "lots of blood",
    "unconscious", "passed out", "fainted",
    "seizure", "convulsion", "fitting",
    "stroke", "face drooping", "arm weakness",
    "not breathing", "stopped breathing",
    # Nigerian Pidgin emergency phrases
    "i dey die", "i wan die", "e dey pain me well well",
    "my body dey shake bad", "blood dey come out",
    "i never wake up well", "i fall down",
]

class HealthcareAssistantError(Exception):
    """Base error for the pipeline."""

class AgentCallError(HealthcareAssistantError):
    """Raised when an API call fails after all retries."""

class JSONParseError(HealthcareAssistantError):
    """Raised when the model returns malformed JSON."""

class AuthenticationError(HealthcareAssistantError):
    """Raised when the API key is missing or invalid."""

from groq import Groq

GROQ_API_KEY = [
    os.getenv("GROQ_API_KEY_1"),
    os.getenv("GROQ_API_KEY_2"), 
    os.getenv("GROQ_API_KEY_3"),    
]

key_pool = itertools.cycle(GROQ_API_KEY)

_groq_client: Optional[Groq] = None


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:

        key = next(key_pool)
        if not key:
            raise AuthenticationError(
                "Set GROQ_API_KEY (or GROK_API_KEY) in your environment or .env file."
            )
        _groq_client = Groq(api_key=key, timeout=30)
    return _groq_client


def call_llm(
    system_prompt: str,
    user_message: str,
    retries: int = 3,
    backoff: float = 2.0,
    *,
    json_mode: bool = False,
    max_completion_tokens: Optional[int] = None,
) -> str:
    """Call the Groq/Llama LLM with retry logic.

    Use json_mode=True for agents that must return JSON; Groq then emits a single
    valid JSON object, which avoids cut-off strings like ``"reasoning": "These``.
    """
    client = _get_groq_client()
    cap = max_completion_tokens if max_completion_tokens is not None else MAX_TOKENS
    extra: dict = {"max_completion_tokens": cap}
    if json_mode:
        extra["response_format"] = {"type": "json_object"}

    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                **extra,
            )
            content = (response.choices[0].message.content or "").strip()
            return content
        except Exception as e:
            logging.warning("[LLM] Attempt %d/%d failed: %s", attempt, retries, e)
            if attempt == retries:
                raise AgentCallError(f"Groq API failed after {retries} attempts: {e}") from e
            time.sleep(backoff * attempt)


def _llm_json(system_prompt: str, user_message: str, agent_name: str, parse_retries: int = 3) -> dict:
    """Call LLM in JSON mode and parse; retry the whole call if output is still invalid."""
    last_err: Optional[BaseException] = None
    for p in range(parse_retries):
        raw = call_llm(system_prompt, user_message, json_mode=True)
        try:
            return parse_json_response(raw, agent_name=agent_name)
        except JSONParseError as e:
            last_err = e
            logging.warning(
                "[%s] Invalid JSON from model (attempt %d/%d), retrying…",
                agent_name,
                p + 1,
                parse_retries,
            )
            time.sleep(1.0 * (p + 1))
    assert last_err is not None
    raise last_err


def parse_json_response(raw: str, agent_name: str = "unknown") -> dict:
    """Strip markdown fences and parse JSON. Raises JSONParseError on failure."""
    try:
        cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logging.error("[%s] JSON parse failed. Raw output: %s", agent_name, raw[:300])
        raise JSONParseError(f"Agent '{agent_name}' returned malformed JSON: {e}") from e


def check_emergency(text: str) -> Optional[dict]:
    """Return an emergency dict if any keyword matches, else None."""
    lower = text.lower()
    for kw in EMERGENCY_KEYWORDS:
        if kw in lower:
            return {
                "emergency": True,
                "message": (
                    "This may be a medical emergency. "
                    "Please go to the nearest hospital or call emergency services immediately."
                ),
            }
    return None