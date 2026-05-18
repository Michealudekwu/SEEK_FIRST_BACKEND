# Seek — Agent Pipeline

This document describes the full AI agent pipeline: how each agent works, what it receives, what it returns, and how the three API flows compose them.

---

## Overview

The pipeline is split across **two user-facing flows** and one optional **report flow**. Each flow is executed as a Celery task so the FastAPI server never blocks on LLM calls.

```
User Input (symptoms)
       │
       ▼
 ┌─────────────────┐
 │ Emergency Check │  ──── match found ──▶  EMERGENCY response (no LLM called)
 └────────┬────────┘
          │ no match
          ▼
      START FLOW
  ┌────────────────┐
  │   Agent 1      │  Struct Agent — structures raw text into typed symptom JSON
  └───────┬────────┘
          │
          ▼
  ┌────────────────┐
  │   Agent 1.5    │  QA Agent — generates 2–4 clarifying questions
  └───────┬────────┘
          │
          ▼
    ← returns to user with questions →

          │  user submits answers
          ▼
      COMPLETE FLOW
  ┌────────────────┐
  │   Agent 1.5    │  Synthesiser — merges original symptoms + Q&A into enriched profile
  └───────┬────────┘
          │
          ▼
  ┌────────────────┐
  │   Agent 2      │  Clinical Agent — probabilistic differential diagnosis
  └───────┬────────┘
          │
          ▼
  ┌────────────────┐
  │   Agent 3      │  Simplify Agent — converts clinical JSON to plain English or Pidgin
  └───────┬────────┘
          │
          ▼
    ← returns to user with simplified message →

          │  user requests referral note  (optional)
          ▼
      DOCTORS REPORT FLOW
  ┌────────────────┐
  │   Agent 4      │  Doctors Rep — rewrites enriched symptoms as a clinical referral note
  └───────┬────────┘
          │
          ▼
    ← returns doctors_report string →
```

---

## Emergency Check

**File:** `agents/agent_call.py` → `check_emergency(text)`

Runs a keyword scan against a hardcoded list before any LLM is called. Covers standard English emergency phrases and Nigerian Pidgin equivalents (e.g. `"i dey die"`, `"blood dey come out"`).

If matched, the pipeline short-circuits immediately and returns:
```json
{
  "stage": "emergency",
  "emergency": true,
  "message": "This may be a medical emergency. Please go to the nearest hospital or call emergency services immediately."
}
```

No LLM tokens are consumed for emergencies.

---

## Agent 1 — Symptom Structurer

**File:** `agents/struct_agent.py`
**Called in:** `run_start_pipeline` (Celery task for `POST /api/start`)

Takes the user's raw free-text symptom description and converts it into a typed, validated JSON object.

**Input:** plain text (English or Pidgin)

**Output:**
```json
{
  "symptoms": ["fever", "headache", "body aches"],
  "severity": "moderate",
  "duration": "2 days",
  "risk_flags": false,
  "detected_language": "english"
}
```

`risk_flags` is set to `true` if any of the following are present: high fever, blood in stool/urine/vomit, confusion, difficulty breathing, chest pain, severe abdominal pain, or symptoms lasting over 7 days.

`detected_language` is carried forward through the entire pipeline and used by Agent 3 to choose the correct output language.

---

## Agent 1.5 — QA Agent (two sub-modes)

**File:** `agents/QA_agent.py`

This agent runs in two separate modes at different stages of the pipeline.

### Mode A: Question Generator
**Called in:** `run_start_pipeline`

Receives the structured symptom JSON from Agent 1 and identifies what clinical information is missing. Generates 2–4 short, plain-language follow-up questions targeting gaps like onset pattern, pain character, recent travel, dietary changes, and sick contacts.

If `detected_language` is `"pidgin"`, questions are written in Nigerian Pidgin English.

**Output:**
```json
{
  "questions": [
    { "id": 1, "text": "When exactly did the symptoms start?" },
    { "id": 2, "text": "Have you been near anyone else who is sick?" }
  ],
  "reasoning": "Clarifying onset and exposure to distinguish malaria from typhoid."
}
```

### Mode B: Synthesiser
**Called in:** `run_complete_pipeline`

Receives the original structured symptoms, the list of questions that were asked, and the patient's free-text answers. Merges everything into an enriched symptom profile with an `additional_context` block.

**Output:**
```json
{
  "symptoms": ["fever", "headache", "body aches"],
  "severity": "moderate",
  "duration": "2 days",
  "risk_flags": false,
  "detected_language": "english",
  "additional_context": {
    "onset_pattern": "sudden",
    "associated_symptoms": ["chills", "loss of appetite"],
    "relevant_history": "ate street food 2 days ago",
    "pain_character": "throbbing",
    "similar_contacts_sick": false,
    "triggers_or_relievers": "worse in the evenings"
  }
}
```

---

## Agent 2 — Clinical Reasoning

**File:** `agents/clinical_agent.py`
**Called in:** `run_complete_pipeline`

Takes the enriched symptom profile from Agent 1.5 (Synthesiser) and performs probabilistic differential diagnosis. Operates with a Nigerian epidemiological prior — malaria, typhoid fever, dehydration, food poisoning, respiratory infections, and peptic ulcer disease are given higher baseline likelihood.

Strict prompt rules:
- Never says "you have X" — uses "consistent with" or "could possibly be"
- Never prescribes drugs or dosages
- Never claims certainty

**Output:**
```json
{
  "possible_conditions": [
    { "name": "Malaria", "likelihood": "high", "reasoning": "Sudden-onset fever with chills following a history of outdoor exposure is classic for malaria in Nigeria." },
    { "name": "Typhoid fever", "likelihood": "moderate", "reasoning": "Fever with appetite loss and possible contaminated food exposure warrants consideration." }
  ],
  "remedies": ["Stay hydrated", "Rest in a cool room", "Use ORS if vomiting"],
  "warning_signs": ["High fever above 39°C", "Confusion or altered consciousness"],
  "seek_care_urgency": "within 24 hours"
}
```

---

## Agent 3 — Simplifier

**File:** `agents/simplify_agent.py`
**Called in:** `run_complete_pipeline`

Takes the clinical JSON from Agent 2 and converts it into a warm, conversational message no longer than 120 words. Uses two separate system prompts:

- **English prompt** — plain, jargon-free British/Nigerian English
- **Pidgin prompt** — natural Nigerian Pidgin (e.g. `"E be like say..."`, `"no be emergency for now"`)

The language is selected automatically based on `detected_language` from the enriched symptom profile.

Every message ends with a mandatory disclaimer:
- English: *"This is not a medical diagnosis. Please consult a healthcare professional if possible."*
- Pidgin: *"This no be medical diagnosis. Abeg try see health professional if you fit."*

**Output:** plain text string (not JSON)

---

## Agent 4 — Doctor's Report

**File:** `agents/doctors_rep.py`
**Called in:** `run_doctors_report_pipeline` (Celery task for `POST /api/doctors-report`)

Takes the full enriched symptom profile (from `enriched_symptoms` in the complete session result) and rewrites it as a professional clinical referral note that a doctor can read quickly.

Strict prompt rules:
- Clinical phrasing only: "patient reports", "presents with", "onset was", "associated with"
- No diagnosis, no treatment recommendations
- 3–5 sentences, one paragraph
- Ends with "Kindly review and assess."

**Output:** plain text string, e.g.:

> *Patient reports a 2-day history of sudden-onset fever, headache, and generalised body aches, associated with chills and loss of appetite. Onset was abrupt. Patient consumed street food approximately 2 days prior to symptom onset; no similar contacts reported. Symptoms are moderate in severity with no current risk flags identified. Kindly review and assess.*

---

## LLM Infrastructure

**File:** `agents/agent_call.py`

All agents call the same underlying function: `call_llm()`.

- **Model:** `llama-3.3-70b-versatile` via Groq
- **API key rotation:** cycles through up to 3 keys (`GROQ_API_KEY_1/2/3`) using `itertools.cycle` to stay within per-key rate limits
- **JSON mode:** agents that must return JSON use `response_format: json_object`, which prevents truncated strings
- **Retries:** 3 attempts with exponential backoff (`2 * attempt` seconds)
- **Parse retries:** if the model returns malformed JSON even in JSON mode, `_llm_json()` retries the full call up to 3 more times

---

## Task Queue & Caching

**Files:** `celery_app.py`, `cache_store.py`, `tasker.py`

The three Celery tasks map directly to the three pipeline flows:

| Task | Endpoint | Agents called |
|---|---|---|
| `run_start_pipeline` | `POST /api/start` | Emergency check → Agent 1 → Agent 1.5 (questions) |
| `run_complete_pipeline` | `POST /api/complete` | Emergency check → Agent 1.5 (synthesise) → Agent 2 → Agent 3 |
| `run_doctors_report_pipeline` | `POST /api/doctors-report` | Agent 4 |

All tasks have `max_retries=3` with exponential backoff. The FastAPI server polls for the result every 500ms with a 60-second timeout.

The `/api/start` response is cached in Redis for 1 hour, keyed by `"seek:" + MD5(symptoms.lower().strip())`. Identical symptom strings skip the entire pipeline and return the cached result instantly.
