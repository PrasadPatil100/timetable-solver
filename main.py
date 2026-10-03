import logging

from fastapi import FastAPI, HTTPException

from models import SolverRequest, SolverResult
from solver import solve_basic
from validation import validate_solver_request, validate_solver_result


app = FastAPI(title="Timetable Solver API")
logger = logging.getLogger(__name__)


@app.get("/")
def root():
    return {
        "message": "Timetable Solver API is running"
    }


@app.post("/solve", response_model=SolverResult)
def solve_timetable(request: SolverRequest) -> SolverResult:
    request_errors = validate_solver_request(request)
    if request_errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Invalid solver request.", "errors": request_errors},
        )

    try:
        result = solve_basic(request)
    except Exception:
        logger.exception("Timetable solver failed unexpectedly.")
        raise HTTPException(
            status_code=500,
            detail="Timetable solver failed unexpectedly.",
        ) from None

    result_errors = validate_solver_result(request, result)
    if result_errors:
        logger.error("Timetable solver produced an invalid result: %s", result_errors)
        raise HTTPException(
            status_code=500,
            detail="Timetable solver produced an invalid result.",
        )
    return result