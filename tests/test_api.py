"""API endpoint tests. Run with: pytest tests/"""

VALID_SUBMISSION = (
    "Classes: ParkingLot (aggregate root), Floor, ParkingSpot, Vehicle (abstract) with "
    "Motorcycle/Car/Truck subclasses, Ticket, and a FeeCalculator strategy interface. "
    "ParkingLot delegates spot lookup to a SpotFinder so the nearest-spot algorithm can be "
    "swapped. Concurrency: a lock per floor when assigning a spot. If the lot is full we raise "
    "LotFullException. Trade-off: in-memory state for simplicity over persistence."
)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_problems_returns_three(client):
    response = client.get("/problems")
    assert response.status_code == 200
    problems = response.json()
    assert len(problems) == 3
    titles = {p["title"] for p in problems}
    assert titles == {"Parking Lot System", "Elevator System", "Vending Machine"}
    for problem in problems:
        assert set(problem) >= {"id", "title", "description", "requirements", "constraints"}


def test_get_problem_by_id(client):
    response = client.get("/problems/1")
    assert response.status_code == 200
    problem = response.json()
    assert problem["id"] == 1
    assert problem["title"] == "Parking Lot System"
    assert "multiple floors" in problem["requirements"]
    assert "Motorcycle $1/hr" in problem["constraints"]


def test_get_missing_problem_returns_404(client):
    response = client.get("/problems/999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_create_attempt_with_valid_data(client):
    response = client.post("/attempts", json={"problem_id": 1, "submission_text": VALID_SUBMISSION})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"attempt_id", "status", "message"}
    assert body["status"] == "completed"
    assert isinstance(body["attempt_id"], int)

    detail = client.get(f"/attempts/{body['attempt_id']}")
    assert detail.status_code == 200
    attempt = detail.json()
    assert attempt["status"] == "completed"
    assert attempt["problem_id"] == 1
    assert attempt["submission_text"] == VALID_SUBMISSION
    evaluation = attempt["evaluation"]
    assert evaluation is not None
    assert 0 <= evaluation["overall_score"] <= 100
    assert isinstance(evaluation["top_strengths"], list)
    assert isinstance(evaluation["top_improvements"], list)
    assert evaluation["summary"]


def test_create_attempt_missing_problem_id_returns_422(client):
    response = client.post("/attempts", json={"submission_text": VALID_SUBMISSION})
    assert response.status_code == 422


def test_create_attempt_empty_submission_returns_422(client):
    assert client.post("/attempts", json={"problem_id": 1, "submission_text": ""}).status_code == 422
    assert client.post("/attempts", json={"problem_id": 1, "submission_text": "   \n "}).status_code == 422


def test_create_attempt_unknown_problem_returns_404(client):
    response = client.post("/attempts", json={"problem_id": 999, "submission_text": VALID_SUBMISSION})
    assert response.status_code == 404


def test_get_missing_attempt_returns_404(client):
    assert client.get("/attempts/999999").status_code == 404


def test_list_attempts(client):
    client.post("/attempts", json={"problem_id": 2, "submission_text": VALID_SUBMISSION})
    response = client.get("/attempts")
    assert response.status_code == 200
    attempts = response.json()
    assert isinstance(attempts, list)
    assert len(attempts) >= 2
    # Newest first.
    ids = [a["id"] for a in attempts]
    assert ids == sorted(ids, reverse=True)

    filtered = client.get("/attempts", params={"problem_id": 2}).json()
    assert filtered and all(a["problem_id"] == 2 for a in filtered)


def test_history_for_problem(client):
    client.post("/attempts", json={"problem_id": 1, "submission_text": VALID_SUBMISSION + " Second try."})
    response = client.get("/history/1")
    assert response.status_code == 200
    history = response.json()
    assert len(history) >= 2
    assert all(a["problem_id"] == 1 for a in history)
    ids = [a["id"] for a in history]
    assert ids == sorted(ids, reverse=True)
    assert all(a["evaluation"] is not None for a in history if a["status"] == "completed")


def test_history_for_missing_problem_returns_404(client):
    assert client.get("/history/999").status_code == 404
