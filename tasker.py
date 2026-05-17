from celery_app import celery
from agents.struct_agent import agent1_structure_symptoms
from agents.QA_agent import agent1_5_generate_questions, agent1_5_synthesise
from agents.clinical_agent import agent2_clinical_reasoning
from agents.simplify_agent import agent3_simplify
from agents.doctors_rep import generate_doctors_report
from agents.agent_call import check_emergency

@celery.task(bind=True, max_retries=3)
def run_start_pipeline(self, user_text: str):
    try:
        emergency = check_emergency(user_text)
        structured_user_input = agent1_structure_symptoms(user_text)

        if emergency:
            return {
                "stage" : "emergency",
                **emergency
            }
        
        questions = agent1_5_generate_questions(structured_user_input)

        return {
            "stage" : "awaiting_answers",
            "structured_symptoms" : structured_user_input,
            **questions
        }

    except Exception as e:
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
    
@celery.task(bind=True, max_retries=3)
def run_complete_pipeline(self, structured_symptoms, questions, answers):
    try:
        emergency = check_emergency(answers)
        if emergency:
            return {
                "stage" : "emergency",
                **emergency
            }
        
        enriched_symps = agent1_5_synthesise(structured_symptoms, questions, answers)
        detected_language = enriched_symps.get(
            "detected_language",
            structured_symptoms.get("detected_language", "english")
        )

        clinical = agent2_clinical_reasoning(enriched_symps)
        simplified_reply = agent3_simplify(clinical, detected_language)

        return {
            "stage" : "complete",
            "simplified_message" : simplified_reply,
            **clinical,
            "enriched_symptoms" : enriched_symps
        }
    
    except Exception as e:
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
    
@celery.task(bind=True, max_retries=3)
def run_doctors_report_pipeline(self, result):
    try:
        report = generate_doctors_report(result)
        return {
            **report
        }
    
    except Exception as e:
        raise self.retry(exc=e, countdown=2 ** self.request.retries)