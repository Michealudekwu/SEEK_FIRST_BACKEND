import logging
from agents.agent_call import call_llm, AgentCallError


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

AGENT4_SYSTEM = """
You are a medical scribe. A patient has described their symptoms in casual, everyday language.
Your only job is to rewrite what they said as a short, professional clinical referral note
that a doctor can read quickly and understand clearly.

Rules:
- Rewrite the patient's own words into clean medical English.
- Use clinical phrasing: "patient reports", "presents with", "onset was", "associated with".
- Do NOT diagnose. Do NOT recommend treatment. Do NOT add anything the patient did not mention.
- Keep it to 3–5 sentences. One short paragraph. No headings, no bullet points, no lists.
- End with: "Kindly review and assess."

Return ONLY the paragraph. Nothing else.
""".strip()


def agent4_generate_report(enriched_symptoms: dict) -> str:
    """
    Rewrites the patient's symptom profile as a concise clinical referral note.

    Args:
        enriched_symptoms: Output from agent1_5_synthesise()

    Returns:
        A plain-text clinical referral paragraph.
    """
    logging.info("[Agent 4] Generating doctor's report...")

    ctx = enriched_symptoms.get("additional_context", {})

    patient_description = (
        f"Symptoms: {', '.join(enriched_symptoms.get('symptoms', []))}. "
        f"Duration: {enriched_symptoms.get('duration', 'not mentioned')}. "
        f"Severity: {enriched_symptoms.get('severity', 'unknown')}. "
        f"Onset: {ctx.get('onset_pattern', 'not mentioned')}. "
        f"Pain character: {ctx.get('pain_character', 'not applicable')}. "
        f"Associated symptoms: {', '.join(ctx.get('associated_symptoms', [])) or 'none reported'}. "
        f"Relevant history: {ctx.get('relevant_history', 'not mentioned')}. "
        f"Similar contacts sick: {ctx.get('similar_contacts_sick')}. "
        f"Triggers or relievers: {ctx.get('triggers_or_relievers', 'not mentioned')}."
    )

    return call_llm(AGENT4_SYSTEM, patient_description)


def generate_doctors_report(result: dict) -> dict:
    """
    Takes the output of complete_session() and produces a doctor's referral note.

    Args:
        result: The dict returned by complete_session() with stage == "complete"

    Returns:
        The same result dict with a "doctors_report" key added, or an error dict.
    """
    if result.get("error"):
        return result

    if result.get("stage") != "complete":
        return {
            "error": True,
            "message": "generate_doctors_report() requires a completed session. Run complete_session() first.",
        }

    try:
        report = agent4_generate_report(
            enriched_symptoms=result["enriched_symptoms"],
        )
        return {**result, "doctors_report": report}

    except AgentCallError as e:
        logging.error("API call failed during report generation: %s", e)
        return {"error": True, "error_type": "api_failure", "message": "Could not generate the report. Check your connection and try again."}
    except Exception as e:
        logging.exception("Unexpected error in generate_doctors_report: %s", e)
        return {"error": True, "error_type": "unexpected", "message": "An unexpected error occurred while generating the report."}