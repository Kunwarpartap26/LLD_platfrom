"""AI evaluation of LLD submissions against a fixed rubric.

Primary path: Gemini via the google-generativeai SDK.
Fallback path: a deterministic heuristic evaluator used when no GEMINI_API_KEY
is configured (or FORCE_HEURISTIC_EVALUATOR=1). This keeps the platform and the
test-suite runnable offline and is the seam where a rule-based evaluator would
plug in (see design_note.md, change test B).
"""

import json
import os
import re
import warnings
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load backend/.env regardless of the working directory uvicorn/pytest use.
load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv()  # also honour a repo-root .env if present

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# The assignment names gemini-1.5-flash; newer models can be swapped in via env.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
MAX_OUTPUT_TOKENS = 2000

DIMENSIONS: dict[str, int] = {
    "requirement_understanding": 10,
    "class_responsibilities": 20,
    "coupling_cohesion": 15,
    "abstraction_interfaces": 15,
    "extensibility": 20,
    "edge_cases": 10,
    "explanation_quality": 10,
}
REQUIRED_TOP_LEVEL_KEYS = {"overall_score", "evaluation", "top_strengths", "top_improvements", "summary"}


def build_prompt(problem_title: str, problem_requirements: str, problem_constraints: str, submission_text: str) -> str:
    """Return the exact evaluation prompt sent to the model."""
    return f"""You are an expert software design evaluator specializing in Low-Level Design (LLD).

Evaluate the following LLD solution submission. Return ONLY valid JSON, no markdown, no explanation outside the JSON.
Return ONLY raw JSON starting with {{ and ending with }}. No markdown. No code blocks. No text before or after the JSON.

PROBLEM TITLE: {problem_title}

PROBLEM REQUIREMENTS:
{problem_requirements}

PROBLEM CONSTRAINTS:
{problem_constraints}

CANDIDATE SUBMISSION:
{submission_text}

EVALUATION RUBRIC — score each dimension based on specific evidence from the submission:

1. requirement_understanding (max 10 points)
   - Did the candidate address all stated requirements?
   - Are there obvious requirements they missed?
   - Did they make reasonable assumptions for unclear requirements?

2. class_responsibilities (max 20 points)
   - Are classes clearly defined with single responsibilities?
   - Does each class have a clear purpose?
   - Are responsibilities distributed logically?
   - Is there God class anti-pattern present?

3. coupling_cohesion (max 15 points)
   - Are classes loosely coupled?
   - Is cohesion high within classes?
   - Are dependencies minimized and directed correctly?

4. abstraction_interfaces (max 15 points)
   - Are interfaces used appropriately?
   - Is the right level of abstraction chosen?
   - Are implementation details hidden correctly?
   - Are design patterns applied where genuinely helpful?

5. extensibility (max 20 points)
   - Can the design accommodate new requirements without major changes?
   - Does it follow Open/Closed principle?
   - Are extension points identified?

6. edge_cases (max 10 points)
   - Are boundary conditions handled?
   - Are error states considered?
   - Are concurrent access issues addressed if relevant?

7. explanation_quality (max 10 points)
   - Is the reasoning clear and well-articulated?
   - Are trade-offs explained?
   - Is the submission well-organized and readable?

IMPORTANT RULES FOR EVALUATION:
- Multiple valid designs exist — do not penalize for not matching a reference solution
- Base every score and comment on specific evidence found in the submission
- If the submission is too vague to evaluate a criterion properly, give a low score and explain what is missing
- Never give 100/100 — every design has room for improvement
- confidence field: use "high" if you found clear evidence, "medium" if you inferred, "low" if you guessed

Return this exact JSON structure and nothing else:
{{
  "overall_score": <integer 0-100, sum of all dimension scores>,
  "evaluation": {{
    "requirement_understanding": {{
      "score": <0-10>,
      "evidence": "<direct quote or specific observation from the submission>",
      "concern": "<what is missing or problematic>",
      "suggestion": "<specific actionable improvement>",
      "confidence": "<high|medium|low>"
    }},
    "class_responsibilities": {{
      "score": <0-20>,
      "evidence": "...",
      "concern": "...",
      "suggestion": "...",
      "confidence": "..."
    }},
    "coupling_cohesion": {{
      "score": <0-15>,
      "evidence": "...",
      "concern": "...",
      "suggestion": "...",
      "confidence": "..."
    }},
    "abstraction_interfaces": {{
      "score": <0-15>,
      "evidence": "...",
      "concern": "...",
      "suggestion": "...",
      "confidence": "..."
    }},
    "extensibility": {{
      "score": <0-20>,
      "evidence": "...",
      "concern": "...",
      "suggestion": "...",
      "confidence": "..."
    }},
    "edge_cases": {{
      "score": <0-10>,
      "evidence": "...",
      "concern": "...",
      "suggestion": "...",
      "confidence": "..."
    }},
    "explanation_quality": {{
      "score": <0-10>,
      "evidence": "...",
      "concern": "...",
      "suggestion": "...",
      "confidence": "..."
    }}
  }},
  "top_strengths": ["<strength 1>", "<strength 2>"],
  "top_improvements": ["<improvement 1>", "<improvement 2>", "<improvement 3>"],
  "summary": "<2-3 sentences: what the candidate did well, what to focus on next time>"
}}
"""


# --------------------------------------------------------------------------- #
# Response parsing / normalisation
# --------------------------------------------------------------------------- #

def _extract_json(text: str) -> dict[str, Any]:
    """Parse model output into a dict, tolerating ```json fences and prose."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Last resort: grab the outermost {...} block.
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


def _clamp(value: Any, low: int, high: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def normalize_result(parsed: dict[str, Any]) -> dict[str, Any]:
    """Validate shape, clamp scores to rubric maxima and recompute the total.

    The model is asked for a sum, but we never trust arithmetic from an LLM:
    the stored overall_score is always the sum of the clamped dimension scores.
    """
    missing = REQUIRED_TOP_LEVEL_KEYS - set(parsed)
    if missing:
        raise ValueError(f"AI response missing keys: {sorted(missing)}")

    raw_eval = parsed.get("evaluation") or {}
    evaluation: dict[str, dict[str, Any]] = {}
    total = 0
    for name, max_score in DIMENSIONS.items():
        dim = raw_eval.get(name)
        if not isinstance(dim, dict):
            raise ValueError(f"AI response missing dimension: {name}")
        score = _clamp(dim.get("score"), 0, max_score)
        total += score
        evaluation[name] = {
            "score": score,
            "max_score": max_score,
            "evidence": str(dim.get("evidence") or "").strip(),
            "concern": str(dim.get("concern") or "").strip(),
            "suggestion": str(dim.get("suggestion") or "").strip(),
            "confidence": str(dim.get("confidence") or "medium").lower(),
        }

    def as_str_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    return {
        "status": "completed",
        # Rubric rule: never award a perfect score.
        "overall_score": min(total, 99),
        "evaluation": evaluation,
        "top_strengths": as_str_list(parsed.get("top_strengths")),
        "top_improvements": as_str_list(parsed.get("top_improvements")),
        "summary": str(parsed.get("summary") or "").strip(),
    }


# --------------------------------------------------------------------------- #
# Heuristic fallback (no API key)
# --------------------------------------------------------------------------- #

_KEYWORDS: dict[str, list[str]] = {
    "requirement_understanding": ["requirement", "assume", "assumption", "support", "must", "should"],
    "class_responsibilities": ["class", "responsib", "single responsibility", "manager", "service", "entity"],
    "coupling_cohesion": ["couple", "cohesion", "depend", "inject", "composition", "aggregat"],
    "abstraction_interfaces": ["interface", "abstract", "strategy", "factory", "observer", "state pattern", "polymorph", "encapsulat"],
    "extensibility": ["extend", "extensib", "open/closed", "open-closed", "plug", "new type", "without modifying", "future"],
    "edge_cases": ["edge", "concurren", "lock", "thread", "full", "invalid", "error", "exception", "empty", "boundary", "race"],
    "explanation_quality": ["trade-off", "tradeoff", "because", "rationale", "alternative", "why", "chose"],
}


def heuristic_evaluate(submission_text: str) -> dict[str, Any]:
    """Cheap, deterministic, keyword-driven scoring.

    Deliberately conservative: it cannot judge design quality, so it rewards
    coverage of rubric vocabulary and length, and says so in its evidence.
    """
    text = submission_text.lower()
    length = len(submission_text.strip())
    # Length factor: ~0 for tiny inputs, saturates around 1500 chars.
    length_factor = min(1.0, length / 1500)

    evaluation: dict[str, dict[str, Any]] = {}
    for name, max_score in DIMENSIONS.items():
        hits = [kw for kw in _KEYWORDS[name] if kw in text]
        coverage = min(1.0, len(hits) / 3)
        # 70% weight on vocabulary coverage, 30% on overall depth (length).
        score = int(round(max_score * (0.7 * coverage + 0.3 * length_factor)))
        score = min(score, max_score - 1) if max_score > 1 else score
        label = name.replace("_", " ")
        if hits:
            evidence = f"Submission mentions: {', '.join(hits[:3])}."
        else:
            evidence = f"No discussion of {label} was found in the submission."
        evaluation[name] = {
            "score": score,
            "max_score": max_score,
            "evidence": evidence,
            "concern": (
                f"Heuristic evaluator (no GEMINI_API_KEY configured) could only check for "
                f"{label} vocabulary, not the quality of the reasoning."
            ),
            "suggestion": f"Explicitly address {label} with concrete class/method level detail.",
            "confidence": "low",
        }

    total = sum(d["score"] for d in evaluation.values())
    ranked = sorted(evaluation.items(), key=lambda kv: kv[1]["score"] / kv[1]["max_score"])
    weakest = [k.replace("_", " ") for k, _ in ranked[:3]]
    strongest = [k.replace("_", " ") for k, _ in ranked[-2:] if evaluation[k]["score"] > 0]

    return {
        "status": "completed",
        "overall_score": min(total, 99),
        "evaluation": evaluation,
        "top_strengths": [f"Covers {s}" for s in strongest] or ["Submitted an attempt"],
        "top_improvements": [f"Expand on {w}" for w in weakest],
        "summary": (
            "This is a heuristic (offline) evaluation because no GEMINI_API_KEY is configured. "
            f"The submission is {length} characters long and touches "
            f"{sum(1 for d in evaluation.values() if d['score'] > 0)} of 7 rubric areas. "
            "Configure a Gemini key for evidence-based AI feedback."
        ),
        "evaluator": "heuristic",
    }


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def _use_heuristic() -> bool:
    return os.getenv("FORCE_HEURISTIC_EVALUATOR") == "1" or not GEMINI_API_KEY


def evaluate_submission(
    problem_title: str,
    problem_requirements: str,
    problem_constraints: str,
    submission_text: str,
) -> dict[str, Any]:
    """Evaluate a submission and return a normalised result dict.

    On success: {"status": "completed", "overall_score", "evaluation", ...,
                 "raw_response": <model text>}
    On failure: {"status": "failed", "error": "<message>", "raw_response": ...}
    """
    if _use_heuristic():
        result = heuristic_evaluate(submission_text)
        result["raw_response"] = json.dumps(result, indent=2)
        return result

    prompt = build_prompt(problem_title, problem_requirements, problem_constraints, submission_text)
    raw_text = ""
    try:
        with warnings.catch_warnings():
            # google-generativeai emits a deprecation FutureWarning on import.
            warnings.simplefilter("ignore", FutureWarning)
            import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            prompt,
            generation_config={
                 "max_output_tokens": MAX_OUTPUT_TOKENS,
                  "temperature": 0.2,
            },
        )
        raw_text = response.text or ""
        parsed = _extract_json(raw_text)
        result = normalize_result(parsed)
        result["evaluator"] = GEMINI_MODEL
        result["raw_response"] = raw_text
        return result
    except json.JSONDecodeError as exc:
        return {"status": "failed", "error": f"AI returned non-JSON output: {exc}", "raw_response": raw_text}
    except ValueError as exc:
        return {"status": "failed", "error": str(exc), "raw_response": raw_text}
    except Exception as exc:  # network errors, auth errors, quota, etc.
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "raw_response": raw_text}
