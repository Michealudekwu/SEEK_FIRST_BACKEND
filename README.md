# Seek Backend

A FastAPI-powered medical triage backend built for Nigerian patients. Users describe their symptoms in plain English or Nigerian Pidgin, and the system guides them through a multi-step AI agent pipeline that returns a personalised health assessment — and optionally a clinical referral note for a doctor.

---

## Features

- Accepts symptoms in **English or Nigerian Pidgin**
- Detects **emergency keywords** instantly (including Nigerian Pidgin phrases) and escalates before any LLM call
- Multi-step **AI agent pipeline** that structures, clarifies, reasons, and simplifies
- Generates a professional **doctor's referral note** on demand
- **Redis caching** of `/api/start` responses (1-hour TTL, keyed by MD5 of symptoms)
- **Celery** task queue with automatic retries — the FastAPI server never blocks on LLM calls
- Rotates across up to **3 Groq API keys** to stay within rate limits
- Returns all LLM output in **JSON mode** to prevent truncation

---

## Tech Stack

| Layer | Technology |
|---|---|
| API server | FastAPI + Uvicorn |
| Task queue | Celery |
| Broker / Cache | Redis |
| LLM provider | Groq (`llama-3.3-70b-versatile`) |
| Data validation | Pydantic |
| Deployment | Procfile (web + worker dyno) |

---

## Project Structure

```
seek_backend/
├── main.py            # FastAPI app — 3 endpoints
├── schema.py          # Pydantic request models
├── tasker.py          # Celery tasks (pipeline orchestration)
├── celery_app.py      # Celery + Redis configuration
├── cache_store.py     # Redis client + cache-key generation
├── procfile           # Web and worker process definitions
├── requirements.txt   # Python dependencies
├── .env               # Environment variables (not committed)
└── agents/
    ├── agent_call.py       # Groq client, call_llm(), emergency checker
    ├── struct_agent.py     # Agent 1 — symptom structurer
    ├── QA_agent.py         # Agent 1.5 — Q&A generator + synthesiser
    ├── clinical_agent.py   # Agent 2 — clinical reasoning
    ├── simplify_agent.py   # Agent 3 — plain-language simplifier
    └── doctors_rep.py      # Agent 4 — doctor's referral note
```

---

## API Endpoints

### `POST /api/start`
Accepts a free-text symptom description, checks for emergencies, structures the input, and returns follow-up questions.

**Request body**
```json
{ "symptoms": "I have headache and fever since 2 days" }
```

**Success response** (`stage: awaiting_answers`)
```json
{
  "stage": "awaiting_answers",
  "structured_symptoms": { ... },
  "questions": [
    { "id": 1, "text": "When did the headache start?" },
    { "id": 2, "text": "Have you had any vomiting?" }
  ],
  "reasoning": "Clarifying onset and associated symptoms to distinguish malaria from typhoid."
}
```

**Emergency response**
```json
{
  "stage": "emergency",
  "emergency": true,
  "message": "This may be a medical emergency. Please go to the nearest hospital or call emergency services immediately."
}
```

---

### `POST /api/complete`
Accepts the structured symptoms, the questions, and the patient's answers. Runs synthesis → clinical reasoning → simplification.

**Request body**
```json
{
  "structured_symptoms": { ... },
  "questions": [ ... ],
  "answers": "The headache started suddenly, I haven't vomited"
}
```

**Success response** (`stage: complete`)
```json
{
  "stage": "complete",
  "simplified_message": "It sounds like you may have ...",
  "possible_conditions": [ ... ],
  "remedies": [ ... ],
  "warning_signs": [ ... ],
  "seek_care_urgency": "within 24 hours",
  "enriched_symptoms": { ... }
}
```

---

### `POST /api/doctors-report`
Takes the complete session result and returns a professional clinical referral note.

**Request body**
```json
{ "result": { <output of /api/complete> } }
```

**Success response**
```json
{
  "stage": "complete",
  "doctors_report": "Patient reports a 2-day history of headache and fever with sudden onset...",
  ...
}
```

---

## Environment Variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY_1=gsk_...
GROQ_API_KEY_2=gsk_...
GROQ_API_KEY_3=gsk_...
REDIS_URL=redis://localhost:6379/2
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://yourfrontend.com
```

---

## Running Locally

**Prerequisites:** Python 3.12+, Redis running locally.

```bash
# 1. Clone and install
git clone <repo-url>
cd seek_backend
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env  # fill in your keys

# 3. Start the Celery worker (separate terminal)
celery -A celery_app worker --loglevel=info --pool=solo

# 4. Start the API server
uvicorn main:app --reload --port 8000
```

---

## Deployment

The `procfile` defines two processes for platforms like Heroku or Railway:

```
web:    uvicorn main:app --host 0.0.0.0 --port $PORT
worker: celery -A celery_app worker --loglevel=info --pool=solo
```

Both must run simultaneously. The web dyno receives requests and dispatches Celery tasks; the worker dyno executes the LLM pipeline.

---

## Safety & Disclaimers

- The system **never diagnoses**. All responses use probabilistic language ("consistent with", "could possibly be").
- The system **never prescribes** specific drugs or dosages.
- Every simplified response ends with: *"This is not a medical diagnosis. Please consult a healthcare professional if possible."*
- Emergency keyword detection runs **before** any LLM call, ensuring the fastest possible escalation for life-threatening inputs.
