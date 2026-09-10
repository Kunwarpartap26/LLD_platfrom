# Design Note

## 1. MVP scope decision

**In scope**

- Three seeded LLD problems (Parking Lot, Elevator, Vending Machine).
- Text submission with a 100-character minimum.
- Synchronous AI evaluation against a fixed 7-dimension rubric; every dimension returns score, evidence, concern, suggestion, confidence.
- Persisted attempts and evaluations; per-problem history with expandable feedback.
- Single-file frontend that runs from disk; FastAPI + SQLite backend; offline test-suite.

**Deliberately out of scope**

- Users/auth, diagram submission, streaming or async evaluation, a problem-authoring UI, comparison of two attempts side by side, and exporting feedback.

The cut line was: *everything needed to validate that structured AI feedback on a text design is useful enough to trigger a second attempt* — and nothing else. Each excluded feature is additive and, as shown in sections 5–6, the data model already leaves room for the two most likely ones.

## 2. Domain model

```
Problem 1 ──< Attempt 1 ──── 1 Evaluation
```

### `Problem`
`id, title, description, requirements, constraints, created_at`

Requirements and constraints are separate text fields rather than one blob because the evaluator prompt treats them differently ("did they address the requirements?" vs "did they respect the constraints/edge cases?"). They are stored as newline-separated bullets; the frontend splits them for display. If problems later need structured metadata (difficulty, tags, hints) those become new columns, not a rewrite.

### `Attempt`
`id, problem_id (FK), submission_text, status, created_at, updated_at`

An attempt is *the learner's act of submitting*, independent of whether evaluation succeeded. `status` is a small state machine — `submitted → evaluating → completed | failed` — which:

- lets a failed AI call be recorded honestly (the attempt exists, the evaluation does not);
- is already sufficient for an asynchronous pipeline (a worker moves the status; the client polls) with no schema change.

### `Evaluation`
`id, attempt_id (FK, unique), overall_score, 7 × {score, evidence, concern, suggestion}, top_strengths, top_improvements, summary, raw_ai_response, created_at`

Kept as a separate table with a one-to-one relationship instead of columns on `Attempt` because:

1. An attempt may legitimately have **no** evaluation (`failed`), and nullable-everything on `Attempt` would be ugly.
2. It allows **more than one evaluator per attempt** in future by relaxing the unique constraint or adding an `evaluator` column (see change test B), without touching `Attempt`.
3. Flat, typed columns per dimension keep scores `NOT NULL`, make aggregate queries trivial, and let the schema itself document the rubric. `raw_ai_response` is retained so an evaluation can be re-parsed if the parser or rubric wording changes.

`top_strengths` / `top_improvements` are JSON arrays serialised to text: SQLite has no array type, they are only ever read whole, and Pydantic re-hydrates them at the API boundary.

## 3. Submission format: text, and why

- **It is what interviews actually produce.** Most remote LLD rounds are a shared doc or a whiteboard narrated in prose; class lists, method signatures and trade-offs are written as text.
- **It is quotable.** The rubric demands *evidence* for every score. A model can quote a sentence back verbatim; it cannot quote a box on a diagram.
- **Zero tooling cost.** No editor library, no image upload, no parsing. A textarea with a live character count and a minimum length is enough to prevent empty or trivial submissions (`AttemptCreate` also rejects whitespace-only text server-side).
- **Code is allowed but not required.** Learners can paste pseudo-code or real classes; the evaluator is told to judge design, not syntax.

The cost is that some learners think visually first; that is addressed in change test A.

## 4. Evaluation approach: deterministic vs AI split

The evaluation pipeline is intentionally layered:

| Layer | Responsibility | Deterministic? |
| --- | --- | --- |
| **Input validation** (`schemas.AttemptCreate`, frontend min length) | Reject empty / trivial input before spending an API call | Yes |
| **Prompt construction** (`evaluator.build_prompt`) | Inject problem + rubric + hard rules ("never 100", "evidence required", "multiple valid designs") | Yes |
| **Judgement** (Gemini, or the heuristic fallback) | Produce per-dimension scores and commentary | No (AI) / Yes (heuristic) |
| **Normalisation** (`evaluator.normalize_result`) | Validate JSON shape, clamp every score to its rubric max, recompute the sum, cap at 99, coerce lists/strings | Yes |
| **Persistence** (`main.evaluation_from_result`) | Flatten to columns; mark attempt `completed` / `failed` | Yes |

The principle: **anything that can be enforced in code is enforced in code.** The model is trusted for judgement and language, never for arithmetic, ranges or schema compliance. This is why the tests can assert `overall_score == sum(dimensions)` and `< 100` regardless of which evaluator ran.

The heuristic evaluator that runs when no API key is present is the first, tiny member of the deterministic-judgement family. It scores vocabulary coverage per dimension, labels every field as low-confidence heuristic output, and exists so the platform is testable and demoable offline.

## 5. Change test A — add diagram submission

**Requirement:** learners can attach a UML/class diagram (image or Mermaid/PlantUML text) alongside or instead of prose.

**What changes**

1. **`Attempt`** gains `submission_format` (`"text" | "text+diagram" | "mermaid"`) and `diagram_path` / `diagram_source` (nullable). `submission_text` becomes nullable *or* keeps a minimum only when no diagram is present — the validator in `AttemptCreate` becomes "at least one of text or diagram".
2. **Upload:** a new `POST /attempts/{id}/diagram` (multipart) or a `diagram_base64` field on `AttemptCreate`; files land on disk / object storage, only the path is stored.
3. **Evaluator:** `evaluate_submission` gains an optional `diagram` argument. For Mermaid/PlantUML the source is simply appended to the prompt under `CANDIDATE DIAGRAM (Mermaid):`. For images, Gemini is multimodal: the image part is passed alongside the text prompt. `build_prompt` remains the single place the rubric lives.
4. **Frontend:** a file input / Mermaid textarea next to the existing textarea; history view renders the diagram.

**What does not change:** `Problem`, `Evaluation`, the rubric, normalisation, every read endpoint, and the tests for them. The separation of *attempt* (what was submitted) from *evaluation* (what was judged) is what keeps this additive.

## 6. Change test B — add a rule-based evaluator

**Requirement:** run deterministic checks alongside the AI (e.g. "constraints mention concurrency but the submission never does", "no class names detected", "fee rates hard-coded in a class instead of configurable") and surface them to the learner.

**What changes**

1. **Evaluator interface.** `evaluate_submission(...) -> dict` is already the contract. Introduce `evaluator/base.py` with a `Protocol` (`evaluate(problem, submission) -> EvaluationResult`) and move the Gemini and heuristic implementations behind it; the existing heuristic fallback is literally the first rule-based evaluator, so this is a refactor rather than new territory.
2. **Composition.** A `CompositeEvaluator` runs the rule-based pass first (cheap, instant) and the AI pass second, then merges: rule findings can (a) be appended to `concern`/`suggestion` of the relevant dimension, (b) cap a dimension (e.g. `edge_cases ≤ 4` when concurrency is required but absent), and/or (c) short-circuit — skip the AI call for submissions that fail basic sanity rules and return only rule feedback.
3. **Persistence.** Add `evaluator` (`"gemini-1.5-flash" | "rules-v1" | "composite"`) to `Evaluation`. Either keep one merged row per attempt (simplest; unique constraint stays) or drop the unique constraint on `attempt_id` to store one row per evaluator and let the API return a list. The `raw_ai_response` column already stores whatever the evaluator emitted, so rule findings can be kept in full.
4. **API/Frontend.** `EvaluationResponse` gains `evaluator` and an optional `rule_findings: list[str]`; the feedback screen shows them as a third list next to strengths/improvements.

**What does not change:** `Problem`, `Attempt`, submission flow, all endpoints' shapes for existing fields. Because normalisation (`normalize_result`) already sits between *any* judgement source and the DB, rule-based scores go through exactly the same clamping and summing.

## 7. Trade-offs and limitations

| Decision | Benefit | Cost |
| --- | --- | --- |
| Synchronous evaluation | Simplest possible flow; no worker, no polling | Request blocks 5–20 s; a slow model degrades the UI. Upgrade path documented in `main.py`. |
| SQLite | Zero setup, file-based, perfect for a 2-day prototype | Single-writer; concurrency and multi-instance deployment need Postgres (SQLAlchemy makes this a URL change). |
| Flat evaluation columns | Typed, queryable, self-documenting | Adding a rubric dimension is a migration, not a config change. Accepted because the rubric *should* change rarely and deliberately. |
| Server-side clamping / sum / cap at 99 | Grading contract is guaranteed by code | The model's own `overall_score` is discarded; if it wanted to weight dimensions differently that intent is lost (by design). |
| Text-only submissions | Quotable evidence, no tooling | Visual thinkers are under-served until change test A ships. |
| Heuristic fallback when no key | Offline demos and tests; honest labelling | Could be mistaken for real feedback by a careless reader; mitigated by the "Heuristic evaluator" text in every concern and the summary. |
| No auth / global attempts | Nothing to configure | Not shareable or deployable multi-user as-is; needs `User` + `Attempt.user_id`. |
| Model consistency | Temperature 0.2 + clamping reduce variance | Same text can still move a few points between runs; a calibration set of hand-graded submissions would be needed to quantify and tune this. |
| Single-file frontend | Works by double-clicking; no build | No components, no URL routing; would be rewritten in a framework once screens multiply. |
