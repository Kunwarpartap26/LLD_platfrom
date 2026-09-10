"""FastAPI entry point for the LLD Practice Platform."""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload

import evaluator
import schemas
from database import Base, SessionLocal, engine, get_db
from models import Attempt, Evaluation, Problem
from seed_data import seed_if_empty

logger = logging.getLogger("lld_platform")
logging.basicConfig(level=logging.INFO)

FRONTEND_INDEX = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Startup: create tables and seed the 3 problems if the table is empty.
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        inserted = seed_if_empty(db)
        if inserted:
            logger.info("Seeded %d problems", inserted)
    finally:
        db.close()
    yield


app = FastAPI(
    title="LLD Practice Platform API",
    version="1.0.0",
    description="Submit Low-Level Design solutions and receive rubric-based AI feedback.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # frontend is opened from file:// so origin is "null"
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Error handlers
# --------------------------------------------------------------------------- #

@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request", "errors": json.loads(json.dumps(exc.errors(), default=str))},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def get_problem_or_404(db: Session, problem_id: int) -> Problem:
    problem = db.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail=f"Problem {problem_id} not found")
    return problem


def evaluation_from_result(attempt_id: int, result: dict) -> Evaluation:
    """Flatten the nested evaluator dict into Evaluation columns."""
    ev = result["evaluation"]
    # Evaluator key -> DB column prefix (they differ for one dimension).
    prefixes = {
        "requirement_understanding": "requirement_understanding",
        "class_responsibilities": "class_responsibilities",
        "coupling_cohesion": "coupling_cohesion",
        "abstraction_interfaces": "abstraction",
        "extensibility": "extensibility",
        "edge_cases": "edge_cases",
        "explanation_quality": "explanation_quality",
    }
    fields: dict = {}
    for key, prefix in prefixes.items():
        dim = ev[key]
        fields[f"{prefix}_score"] = dim["score"]
        fields[f"{prefix}_evidence"] = dim["evidence"]
        fields[f"{prefix}_concern"] = dim["concern"]
        fields[f"{prefix}_suggestion"] = dim["suggestion"]

    return Evaluation(
        attempt_id=attempt_id,
        overall_score=result["overall_score"],
        top_strengths=json.dumps(result["top_strengths"]),
        top_improvements=json.dumps(result["top_improvements"]),
        summary=result["summary"],
        raw_ai_response=result.get("raw_response", ""),
        **fields,
    )


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def serve_frontend():
    """Convenience: serve the SPA so the whole app runs from one process.

    Opening frontend/index.html directly from disk still works; the page
    falls back to http://localhost:8000 when loaded via file://.
    """
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)
    return {"message": "LLD Practice Platform API. See /docs."}


@app.get("/problems", response_model=list[schemas.ProblemResponse])
def list_problems(db: Session = Depends(get_db)):
    return db.query(Problem).order_by(Problem.id).all()


@app.get("/problems/{problem_id}", response_model=schemas.ProblemResponse)
def get_problem(problem_id: int, db: Session = Depends(get_db)):
    return get_problem_or_404(db, problem_id)


@app.post("/attempts", response_model=schemas.SubmitResponse)
def create_attempt(payload: schemas.AttemptCreate, db: Session = Depends(get_db)):
    problem = get_problem_or_404(db, payload.problem_id)

    attempt = Attempt(problem_id=problem.id, submission_text=payload.submission_text, status="submitted")
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    attempt.status = "evaluating"
    db.commit()

    # NOTE: Evaluation is synchronous for this prototype - the request blocks
    # until the model responds (typically 5-15s). In production this call
    # would be pushed onto a queue (Celery/RQ/SQS) by a worker; the endpoint
    # would return {attempt_id, status: "submitted"} immediately and the
    # frontend would poll GET /attempts/{id} (or subscribe via SSE/WebSocket)
    # until status becomes "completed" or "failed". The Attempt.status state
    # machine already exists so no schema change is needed for that upgrade.
    result = evaluator.evaluate_submission(
        problem_title=problem.title,
        problem_requirements=problem.requirements,
        problem_constraints=problem.constraints,
        submission_text=payload.submission_text,
    )

    if result.get("status") != "completed":
        attempt.status = "failed"
        db.commit()
        logger.warning("Evaluation failed for attempt %s: %s", attempt.id, result.get("error"))
        return schemas.SubmitResponse(
            attempt_id=attempt.id,
            status="failed",
            message=f"Evaluation failed: {result.get('error', 'unknown error')}",
        )

    db.add(evaluation_from_result(attempt.id, result))
    attempt.status = "completed"
    db.commit()

    return schemas.SubmitResponse(
        attempt_id=attempt.id,
        status="completed",
        message="Evaluation complete",
    )


@app.get("/attempts/{attempt_id}", response_model=schemas.AttemptWithEvaluation)
def get_attempt(attempt_id: int, db: Session = Depends(get_db)):
    attempt = (
        db.query(Attempt)
        .options(joinedload(Attempt.evaluation))
        .filter(Attempt.id == attempt_id)
        .first()
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail=f"Attempt {attempt_id} not found")
    return attempt


@app.get("/attempts", response_model=list[schemas.AttemptWithEvaluation])
def list_attempts(problem_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Attempt).options(joinedload(Attempt.evaluation))
    if problem_id is not None:
        query = query.filter(Attempt.problem_id == problem_id)
    return query.order_by(Attempt.created_at.desc(), Attempt.id.desc()).all()


@app.get("/history/{problem_id}", response_model=list[schemas.AttemptWithEvaluation])
def problem_history(problem_id: int, db: Session = Depends(get_db)):
    get_problem_or_404(db, problem_id)
    return (
        db.query(Attempt)
        .options(joinedload(Attempt.evaluation))
        .filter(Attempt.problem_id == problem_id)
        .order_by(Attempt.created_at.desc(), Attempt.id.desc())
        .all()
    )
