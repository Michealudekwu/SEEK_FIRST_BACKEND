import logging
from agents.agent_call import _llm_json
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

AGENT1_5_SYSTEM = """
You are a medical intake assistant helping to clarify a patient's symptoms before a doctor reviews them.
You will receive structured symptom data (JSON) from a first-pass extraction.

Your job:
1. Identify what key clinical information is MISSING that would help distinguish between likely conditions.
2. Generate 2–4 SHORT, plain-language follow-up questions targeting that missing information.
3. Focus on: onset pattern, associated symptoms, relevant history, location/character of pain,
   triggers/relievers, recent travel, dietary changes, and similar contacts who are sick.
4. If the detected_language is "pidgin", write the questions in Nigerian Pidgin English.
5. Do NOT ask about information already present in the symptom data.

Return ONLY valid JSON — no prose, no markdown fences — in this exact schema:
{
  "questions": [
    {"id": 1, "text": "<question>"},
    {"id": 2, "text": "<question>"}
  ],
  "reasoning": "<one short sentence, max 25 words, no line breaks — what clinical gaps you are filling>"
}
Maximum 5 questions. Minimum 2.
""".strip()

AGENT1_5_SYNTHESISE_SYSTEM = """
You are a medical intake assistant. You have:
- Structured symptom data from an initial assessment (JSON)
- A set of follow-up questions that were asked
- The patient's answers to those questions (plain text)

Your job is to merge all this information into one enriched symptom profile.
Incorporate the new details from the answers: refine severity if needed, add new symptoms mentioned,
note relevant history, and flag any new risk indicators.

Return ONLY valid JSON — no prose, no markdown fences — in this exact schema:
{
  "symptoms": ["<symptom>", "..."],
  "severity": "<mild|moderate|severe|unknown>",
  "duration": "<e.g. 3 days>",
  "risk_flags": <true|false>,
  "detected_language": "<english|pidgin>",
  "additional_context": {
    "onset_pattern": "<sudden|gradual|not mentioned>",
    "associated_symptoms": ["<symptom>"],
    "relevant_history": "<e.g. no recent travel, ate street food 2 days ago | not mentioned>",
    "pain_character": "<e.g. sharp, throbbing, cramping | not applicable>",
    "similar_contacts_sick": <true|false|null>,
    "triggers_or_relievers": "<e.g. worse after eating | not mentioned>"
  }
}
""".strip()


def agent1_5_generate_questions(structured_symptoms: dict) -> dict:
    """Generate clarifying follow-up questions based on the structured symptom data."""
    logging.info("[Agent 1.5] Generating follow-up questions...")
    payload = json.dumps(structured_symptoms, indent=2)
    return _llm_json(AGENT1_5_SYSTEM, payload, "Agent1.5-QuestionGenerator")


def agent1_5_synthesise(structured_symptoms: dict, questions: list, answers: str) -> dict:
    """Merge original symptoms + follow-up Q&A into an enriched symptom profile."""
    logging.info("[Agent 1.5] Synthesising follow-up answers...")
    payload = json.dumps({
        "original_symptoms": structured_symptoms,
        "follow_up_questions": questions,
        "patient_answers": answers,
    }, indent=2)
    return _llm_json(AGENT1_5_SYNTHESISE_SYSTEM, payload, "Agent1.5-Synthesiser")
