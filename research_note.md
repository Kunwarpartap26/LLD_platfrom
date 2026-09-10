# Research Note: Practising Low-Level Design

## 1. The problem: why LLD practice is hard

Low-Level Design interviews ask a candidate to turn a fuzzy prompt ("design a parking lot") into classes, responsibilities, relationships and a defensible set of trade-offs, usually in 45 minutes. Unlike algorithmic problems, LLD has three properties that make it hard to *practise*:

1. **There is no single correct answer.** A Strategy-based fee calculator and a table-driven one can both be excellent. Without a reference solution there is no "Accepted" signal, so learners cannot self-check.
2. **The feedback that matters is qualitative.** "Your `ParkingLot` class is doing allocation, billing and persistence" is the useful comment. Nobody tells you that when you practise alone.
3. **Feedback is scarce and slow.** Mock interviews with a senior engineer are expensive and infrequent. Most learners get one or two rounds of real feedback before the actual interview.

The result is a common failure pattern: learners memorise canonical class diagrams for the 10–15 classic problems and can reproduce them, but cannot *explain why* or adapt when the interviewer adds a requirement.

## 2. Existing tools researched

### LeetCode
- **What it does well:** enormous problem bank, instant automated verdicts, discussion threads, contests, streaks. The feedback loop for algorithms is seconds long.
- **LLD coverage:** a handful of "design" tagged problems (LRU cache, Twitter, etc.) are graded purely by functional tests. The grader checks *that* `get()` returns the right value, not *how* the classes are organised. There is no notion of coupling, extensibility or explanation quality.
- **Gap:** optimised for binary correctness; structurally unable to evaluate design quality.

### Grokking the System Design Interview / Grokking the Object-Oriented Design Interview (Educative)
- **What it does well:** curated walkthroughs of the classic problems (parking lot, elevator, vending machine, library, chess…) with use-case lists, class diagrams, activity diagrams and sample code. Excellent as *reading* material.
- **LLD coverage:** high — it is the de-facto syllabus for this space.
- **Gap:** entirely passive. There is one reference solution per problem and no way to submit your own and be told how it differs or where it is weaker. Learners tend to memorise the diagram.

### Educative.io (broader platform)
- **What it does well:** interactive text-based courses, in-browser code execution for implementation exercises, quizzes.
- **LLD coverage:** several courses (the Grokking titles above plus language-specific OOD courses).
- **Gap:** exercises are "fill in this method" with unit tests, or multiple-choice quizzes. Neither evaluates an open-ended design. Feedback is again binary.

### GitHub LLD repositories (e.g. `ashishps1/awesome-low-level-design`, `kumaransg/LLD`, `prasadgujar/low-level-design-primer`)
- **What they do well:** free, community-maintained, dozens of problems with runnable solutions in Java/Python/C++, sometimes with UML. Great for seeing *a* good answer.
- **Gap:** no interactivity at all. You read someone else's code; there is no prompt to attempt it first, no scoring, no history. Quality varies and there is no rubric explaining *why* a solution is good.

### Other things looked at briefly
- **Pramp / interviewing.io:** real peer or expert mock interviews. High-quality feedback but scarce, scheduled, and expensive; not something you can do 10 times in a weekend.
- **ChatGPT / generic LLM chat:** people already paste their designs into a chatbot. The feedback is fluent but unstructured, inconsistent between sessions, has no memory of previous attempts, and tends to be too kind.

## 3. Key gaps found

| Gap | Who has it |
| --- | --- |
| No evaluation of *design quality* (responsibilities, coupling, abstraction, extensibility) — only functional correctness or nothing | LeetCode, Educative exercises, GitHub repos |
| One reference solution presented as "the" answer; alternative valid designs are not recognised | Grokking, GitHub repos |
| No fast, repeatable feedback loop for open-ended text | everyone except paid mocks |
| Feedback is not evidence-based ("you said X, which implies Y") — it is either a verdict or generic advice | LeetCode, generic LLM chat |
| No attempt history, so learners cannot see whether they are improving on a specific weakness | everyone |
| Feedback is not calibrated — a generic chatbot will happily award 95/100 to a vague answer | generic LLM chat |

## 4. Product direction and why

**Direction:** an LLD practice loop where the learner writes a free-text design, and an AI evaluator scores it against a *fixed, published rubric* of seven dimensions (requirement understanding, class responsibilities, coupling/cohesion, abstraction/interfaces, extensibility, edge cases, explanation quality), each with evidence quoted from the submission, a concern, and a concrete suggestion. All attempts are stored per problem so the learner can compare runs.

Why this shape:

1. **The rubric is the product, not the model.** Publishing the dimensions and their weights (class responsibilities and extensibility are worth 20 each; edge cases 10) teaches learners what interviewers actually weigh. It also makes the AI's job narrower and therefore more consistent: it is filling in a form, not free-associating.
2. **Evidence-first feedback closes the "why" gap.** Requiring a quote or specific observation for every score forces the evaluator to ground its judgement in the learner's text, which is the kind of feedback a good interviewer gives and the kind Grokking/GitHub cannot.
3. **Multiple valid designs are explicitly allowed.** The prompt tells the model not to penalise deviation from a reference solution. This is the single biggest difference from test-based graders and from memorise-the-diagram resources.
4. **Text first, diagrams later.** Text is what candidates actually produce in most remote interviews, it is trivially quotable as evidence, and it needs no editor. The data model leaves room for a diagram attachment (see `design_note.md`).
5. **Server-side calibration.** Scores are clamped to rubric maxima, summed on the server and capped below 100 — the platform, not the model, guarantees the grading contract. A rule-based evaluator can be added alongside the AI one for the checks that *are* deterministic (did they mention concurrency when the constraints demand it?).
6. **History makes improvement visible.** Storing every attempt with its full breakdown lets a learner see "edge cases went from 3/10 to 7/10 across three tries", which no existing tool offers.

The MVP deliberately does not include user accounts, diagram upload, streaming responses or a problem authoring UI. Those are all additive; the core hypothesis to validate first is that rubric-structured, evidence-based AI feedback on a text design is useful enough that a learner will do a second attempt.
