"""Evaluator tests.

By default these run against the offline heuristic evaluator (conftest sets
FORCE_HEURISTIC_EVALUATOR=1). To exercise the real Gemini path set
GEMINI_API_KEY and run:  FORCE_HEURISTIC_EVALUATOR=0 pytest tests/test_evaluator.py
"""

import json

import pytest

import evaluator
from evaluator import DIMENSIONS, build_prompt, evaluate_submission, normalize_result

PROBLEM = {
    "problem_title": "Parking Lot System",
    "problem_requirements": "- Support multiple floors\n- Support Motorcycle, Car, Truck\n- Issue tickets\n- Calculate fees",
    "problem_constraints": "- One vehicle per spot\n- Handle concurrency\n- Handle full lot",
}

GOOD_SUBMISSION = """
Classes and responsibilities:
- ParkingLot: aggregate root, owns Floors, exposes park(vehicle) / unpark(ticket).
- Floor: owns a list of ParkingSpot, knows how to find the nearest free spot of a size.
- ParkingSpot: has SpotSize, occupied flag, optional Vehicle. Single responsibility: hold one vehicle.
- Vehicle (abstract) -> Motorcycle, Car, Truck. Each knows its VehicleType and required SpotSize.
- Ticket: id, vehicle, spot, entry time.
- FeeStrategy interface with HourlyFeeStrategy implementation; rates come from a map keyed by VehicleType
  so adding a new vehicle type does not modify the calculator (Open/Closed).
- SpotAllocationStrategy interface (NearestFirst) injected into ParkingLot for extensibility.

Edge cases: lot full -> park() returns Optional.empty / raises LotFullException; ticket not found on exit -> InvalidTicketException.
Concurrency: a ReentrantLock per Floor guards allocation; alternatively an atomic compare-and-set on the spot's occupied flag.
Trade-offs: I chose composition over inheritance for strategies because rates and allocation policies change more often than the class hierarchy.
"""

REQUIRED_KEYS = {"status", "overall_score", "evaluation", "top_strengths", "top_improvements", "summary"}


@pytest.fixture(scope="module")
def result():
    return evaluate_submission(submission_text=GOOD_SUBMISSION, **PROBLEM)


def test_returns_dict_with_required_keys(result):
    assert isinstance(result, dict)
    assert result["status"] == "completed", result.get("error")
    assert REQUIRED_KEYS <= set(result)


def test_overall_score_is_int_in_range(result):
    assert isinstance(result["overall_score"], int)
    assert 0 <= result["overall_score"] <= 100


def test_overall_never_perfect(result):
    assert result["overall_score"] < 100


def test_all_seven_dimensions_present(result):
    evaluation = result["evaluation"]
    assert set(evaluation) == set(DIMENSIONS)
    for name, max_score in DIMENSIONS.items():
        dim = evaluation[name]
        assert set(dim) >= {"score", "evidence", "concern", "suggestion", "confidence"}
        assert isinstance(dim["score"], int)
        assert 0 <= dim["score"] <= max_score


def test_overall_equals_sum_of_dimensions(result):
    total = sum(d["score"] for d in result["evaluation"].values())
    assert result["overall_score"] == min(total, 99)


def test_top_strengths_is_list(result):
    assert isinstance(result["top_strengths"], list)
    assert all(isinstance(s, str) for s in result["top_strengths"])


def test_top_improvements_is_list(result):
    assert isinstance(result["top_improvements"], list)
    assert all(isinstance(s, str) for s in result["top_improvements"])


def test_summary_is_non_empty_string(result):
    assert isinstance(result["summary"], str)
    assert result["summary"].strip()


def test_handles_very_short_submission_gracefully():
    short = evaluate_submission(submission_text="I would use classes.", **PROBLEM)
    assert short["status"] == "completed", short.get("error")
    assert 0 <= short["overall_score"] <= 40, "vague submission should score low"
    assert set(short["evaluation"]) == set(DIMENSIONS)


def test_good_submission_outscores_short_one(result):
    short = evaluate_submission(submission_text="I would use classes.", **PROBLEM)
    assert result["overall_score"] > short["overall_score"]


def test_prompt_contains_problem_and_submission():
    prompt = build_prompt("Elevator System", "- reqs", "- cons", "my design")
    assert "PROBLEM TITLE: Elevator System" in prompt
    assert "- reqs" in prompt and "- cons" in prompt and "my design" in prompt
    for name in DIMENSIONS:
        assert name in prompt
    assert "Never give 100/100" in prompt


def test_normalize_clamps_and_recomputes():
    raw = {
        "overall_score": 100,  # wrong on purpose
        "evaluation": {
            name: {"score": 999, "evidence": "e", "concern": "c", "suggestion": "s", "confidence": "high"}
            for name in DIMENSIONS
        },
        "top_strengths": ["a", ""],
        "top_improvements": "not a list",
        "summary": " ok ",
    }
    normalized = normalize_result(raw)
    for name, max_score in DIMENSIONS.items():
        assert normalized["evaluation"][name]["score"] == max_score
    assert normalized["overall_score"] == 99  # capped below 100
    assert normalized["top_strengths"] == ["a"]
    assert normalized["top_improvements"] == []
    assert normalized["summary"] == "ok"


def test_normalize_rejects_missing_dimension():
    raw = {"overall_score": 1, "evaluation": {}, "top_strengths": [], "top_improvements": [], "summary": "x"}
    with pytest.raises(ValueError):
        normalize_result(raw)


def test_extract_json_tolerates_markdown_fences():
    payload = {"a": 1}
    fenced = "```json\n" + json.dumps(payload) + "\n```"
    assert evaluator._extract_json(fenced) == payload
    prose = "Here you go:\n" + json.dumps(payload) + "\nThanks!"
    assert evaluator._extract_json(prose) == payload


def test_gemini_failure_returns_failed_status(monkeypatch):
    """Simulate a Gemini SDK error and confirm we get a failed dict, not an exception."""
    monkeypatch.setenv("FORCE_HEURISTIC_EVALUATOR", "0")
    monkeypatch.setattr(evaluator, "GEMINI_API_KEY", "fake-key")

    class BrokenModel:
        def __init__(self, *_args, **_kwargs):
            pass

        def generate_content(self, *_args, **_kwargs):
            raise RuntimeError("quota exceeded")

    import google.generativeai as genai

    monkeypatch.setattr(genai, "configure", lambda **_kwargs: None)
    monkeypatch.setattr(genai, "GenerativeModel", BrokenModel)

    failed = evaluate_submission(submission_text=GOOD_SUBMISSION, **PROBLEM)
    assert failed["status"] == "failed"
    assert "quota exceeded" in failed["error"]
