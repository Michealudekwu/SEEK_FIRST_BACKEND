import logging
from agents.agent_call import _llm_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

AGENT1_SYSTEM = """
You are a medical triage assistant specialising in symptom extraction.
Your ONLY job is to parse raw user text and return structured symptom data.
Detect the language of the input (English or Nigerian Pidgin).
Return ONLY valid JSON — no prose, no markdown fences — in this exact schema:
{
  "symptoms": ["<symptom 1>", "..."],
  "severity": "<mild|moderate|severe|unknown>",
  "duration": "<e.g. 2 days | not mentioned>",
  "risk_flags": <true|false>,
  "detected_language": "<english|pidgin>"
}
risk_flags=true if ANY of: high fever, blood in stool/urine/vomit, confusion,
difficulty breathing, chest pain, severe abdominal pain, symptoms lasting over 7 days.
""".strip()


def agent1_structure_symptoms(user_text: str) -> dict:
    logging.info("[Agent 1] Structuring symptoms...")
    return _llm_json(AGENT1_SYSTEM, user_text, "Agent1-SymptomStructurer")