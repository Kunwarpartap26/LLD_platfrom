# AI Usage

AI assistants (v0 / LLM coding tools) were used throughout this assignment for scaffolding, drafting prompts, and reviewing design choices. Below are the five most meaningful AI-assisted decisions, including what was rejected and why.

---

Decision 1: Storing evaluation results in the database
What AI suggested: Store the whole model response as a single JSON column on `Evaluation` (`result_json TEXT`) and parse it in the API layer, "because the shape may change".
What I accepted: Keeping `raw_ai_response` as a verbatim text column so nothing is lost and rows can be re-parsed later.
What I rejected: Making the JSON blob the primary representation.
Why: Flat, typed columns per dimension (`extensibility_score`, `extensibility_evidence`, …) let SQLite enforce `NOT NULL` on scores and make analytics ("average edge-case score for problem 2") a one-line query. Schema rigidity is a feature here: the rubric is the product, and if it changes we *want* a migration, not silent drift inside a blob.

---

Decision 2: Trusting the model's `overall_score`
What AI suggested: The prompt asks the model for `overall_score` as the sum of dimensions, so the first draft of `evaluator.py` simply stored whatever integer came back.
What I accepted: Keeping `overall_score` in the prompt (it forces the model to "commit" to a total and keeps the JSON shape the assignment specifies).
What I rejected: Using that number as-is.
Why: LLMs are unreliable at arithmetic and at respecting per-field ranges. `normalize_result()` now clamps each dimension to its rubric maximum, recomputes the sum server-side, and caps it at 99 to enforce the "never 100/100" rule deterministically instead of hoping the model follows the instruction. Tests (`test_normalize_clamps_and_recomputes`) lock this in.

---

Decision 3: Handling the missing-API-key case
What AI suggested: Return HTTP 500 from `POST /attempts` when `GEMINI_API_KEY` is not set, and mock the Gemini client in tests with `unittest.mock.patch`.
What I accepted: The failure contract — evaluator returns `{"status": "failed", "error": ...}`, the attempt is stored as `failed`, and the API responds 200 with a `failed` status so the UI can preserve the learner's text.
What I rejected: 500 errors and test-only mocks.
Why: A missing key is a configuration state, not a crash; the learner's work should never be lost because of it. Instead of a mock that lives only in tests, I built a small deterministic heuristic evaluator behind the same interface. It makes the app runnable and demoable offline, gives tests real coverage of the persistence path, labels itself honestly in every field (`confidence: "low"`, "Heuristic evaluator…"), and is the concrete plug-in point for the rule-based evaluator described in `design_note.md` change test B.

---

Decision 4: Frontend architecture
What AI suggested: Split the frontend into `index.html`, `styles.css`, `app.js`, and add a tiny hash-router so each screen has a URL.
What I accepted: The idea of a `state` object plus `show(screen)` function as a minimal "router", and `esc()`-ing all API strings before inserting HTML.
What I rejected: Multiple files and URL routing.
Why: The assignment explicitly requires a single `index.html` that works by double-clicking the file. `file://` + multiple files also runs into stricter browser behaviour around module scripts. Four screens toggled with a class is simpler and enough for the MVP; hash routing is a 15-line addition later if bookmarkable attempts become important.

---

Decision 5: Synchronous vs asynchronous evaluation
What AI suggested: Implement `POST /attempts` with FastAPI `BackgroundTasks` so the request returns immediately, and have the frontend poll `GET /attempts/{id}`.
What I accepted: Designing the `Attempt.status` state machine (`submitted → evaluating → completed | failed`) and the `GET /attempts/{id}` endpoint so that polling would work *without a schema change* later.
What I rejected: Doing the async version now.
Why: The assignment asks for synchronous evaluation with a documented upgrade path, and `BackgroundTasks` is a half-measure: it still runs in the web process, is lost on restart, and hides failures. The honest production answer is a real queue (Celery/RQ/SQS) with a worker, which is what the comment in `main.py` describes. Shipping sync with the right data model is a smaller, more truthful step than shipping a fake async.

---

Also used AI for: drafting the seed problem text from the assignment bullets, generating the initial CSS colour tokens, and proof-reading the research/design notes. All code and prompt text was read line by line, run, and tested before being kept.
