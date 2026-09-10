# LLD Practice Platform

A practice platform for Low-Level Design (LLD) interviews. A learner picks a classic problem (Parking Lot, Elevator, Vending Machine), writes their class design as text, and receives a rubric-based evaluation from Gemini with per-dimension scores, evidence, concerns and suggestions. Every attempt is stored so learners can see their history and retry.

```
lld-practice-platform/
├── backend/          FastAPI + SQLAlchemy + SQLite + Gemini evaluator
├── frontend/         Single-file HTML/CSS/JS app (no build step, no dependencies)
├── tests/            pytest suite (API + evaluator)
├── AI_USAGE.md       How AI was used while building this
├── research_note.md  Problem space + existing tools research
└── design_note.md    Domain model, evaluation design, change tests
```

## Setup

1. Clone the repo
2. `cd backend`
3. `pip install -r requirements.txt`
4. Create a `.env` file with `GEMINI_API_KEY=your_key_here` (see `backend/.env.example`)
5. `python seed_data.py`
6. `uvicorn main:app --reload`

The API is now at `http://localhost:8000` (interactive docs at `/docs`). Tables are created and the three problems are seeded automatically on first startup even if you skip step 5.

## Open frontend

Open `frontend/index.html` in your browser (double-click the file). It talks to `http://localhost:8000`.

Alternatively, visit `http://localhost:8000/` — the backend serves the same `index.html`, which is handy when the API runs on a different host/port.

## Run tests

From the repository root:

```
pytest tests/
```

The tests run fully offline: `tests/conftest.py` points the app at a temporary SQLite file and forces the built-in heuristic evaluator, so no API key or network is needed. To exercise the real Gemini code path:

```
FORCE_HEURISTIC_EVALUATOR=0 GEMINI_API_KEY=... pytest tests/test_evaluator.py
```

## Architecture

- **FastAPI backend with SQLite** — three tables: `problems`, `attempts`, `evaluations` (one-to-one with attempts).
- **Gemini API for AI evaluation** — `evaluator.py` builds a fixed rubric prompt, asks for JSON, then validates/clamps every score server-side.
- **Pure HTML/CSS/JS frontend** — one file, four screens (list → detail/submit → feedback → history), `fetch()` only.
- **Synchronous evaluation** — `POST /attempts` blocks until the model responds. See the comment in `main.py::create_attempt` for the async upgrade path (queue + polling; no schema change needed because `Attempt.status` is already a state machine).

### Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness check |
| GET | `/problems` | List all problems |
| GET | `/problems/{id}` | Single problem |
| POST | `/attempts` | Submit a solution; evaluates immediately |
| GET | `/attempts/{id}` | Attempt + evaluation |
| GET | `/attempts?problem_id=` | All attempts (newest first), optional filter |
| GET | `/history/{problem_id}` | Attempts for one problem (newest first) |

## Key Design Decisions

1. **Server-side score normalisation.** The model is asked to return a sum, but `normalize_result()` recomputes `overall_score` from the clamped dimension scores and caps it at 99. LLM arithmetic and range discipline are unreliable; the rubric maxima are the source of truth.
2. **Flat evaluation columns instead of a JSON blob.** Each dimension's score/evidence/concern/suggestion is its own column. This makes "average extensibility score across attempts" a plain SQL query and lets the DB enforce `NOT NULL` on scores. `raw_ai_response` is kept alongside so the row can be re-parsed if the rubric changes.
3. **A pluggable heuristic fallback evaluator.** When `GEMINI_API_KEY` is missing, `evaluator.py` uses a deterministic keyword-coverage scorer that labels itself clearly ("Heuristic evaluator…", confidence `low`). This makes the platform demoable and testable without secrets, and is exactly the seam a rule-based evaluator (design_note.md, change test B) would slot into.
4. **Text submissions, no rich editor.** A textarea with a 100-character minimum keeps the loop fast and lets the evaluator quote the learner verbatim as *evidence*. Diagrams are a planned extension (design_note.md, change test A), not an MVP requirement.

## Limitations

1. **Synchronous evaluation blocks the request** for 5–20 s. Fine for one learner; would need a queue + polling/SSE for real traffic.
2. **No authentication or per-user data.** All attempts are global. Adding a `User` table and `Attempt.user_id` is straightforward but out of scope.
3. **Evaluation consistency is bounded by the model.** Temperature is 0.2 and scores are clamped, but the same submission can still score a few points differently between runs. A calibration set of hand-scored submissions would be needed to measure this.
4. **The heuristic fallback measures vocabulary, not design quality.** It is intentionally conservative and labelled as such; it should never be mistaken for real feedback.
5. **`gemini-1.5-flash` (as specified) is an older model.** The model ID is configurable via `GEMINI_MODEL`; if Google retires it, set e.g. `GEMINI_MODEL=gemini-2.0-flash` in `.env`.

## How to run with a real GEMINI_API_KEY

1. Create a key at <https://aistudio.google.com/app/apikey>.
2. `cp backend/.env.example backend/.env` and set `GEMINI_API_KEY=AIza...`.
3. (Optional) set `GEMINI_MODEL` if you want a different model than `gemini-3.8-flash`.
4. Restart uvicorn. The `/attempts` endpoint now calls Gemini; the feedback screen will show real evidence quotes instead of the "Heuristic evaluator" notice.
5. If a call fails (bad key, quota, model retired) the attempt is stored with `status: "failed"`, the API returns `{"status": "failed", "message": "Evaluation failed: ..."}`, and the UI keeps your text so you can fix the config and resubmit.
