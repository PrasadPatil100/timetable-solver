from fastapi import FastAPI

from models import SolverRequest
from solver import solve_basic


app = FastAPI(title="Timetable Solver API")


@app.get("/")
def root():
    return {
        "message": "Timetable Solver API is running"
    }


@app.post("/solve")
def solve_timetable(request: SolverRequest):

    return solve_basic(request)