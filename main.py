import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import ServiceSettings
from models import SolverRequest, SolverResult
from solver import solve_basic
from validation import validate_solver_request, validate_solver_result


logger = logging.getLogger(__name__)


def create_app(settings: ServiceSettings | None = None) -> FastAPI:
    service_settings = settings or ServiceSettings.from_env()
    service_app = FastAPI(title="Timetable Solver API")
    service_app.add_middleware(
        CORSMiddleware,
        allow_origins=list(service_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @service_app.get("/")
    def root() -> dict[str, str]:
        return {"message": "Timetable Solver API is running"}

    @service_app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "timetable-solver"}

    @service_app.post("/solve", response_model=SolverResult)
    def solve_timetable(request: SolverRequest) -> SolverResult:
        request_errors = validate_solver_request(request)
        if request_errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "Invalid solver request.", "errors": request_errors},
            )

        try:
            result = solve_basic(request)
            result_errors = validate_solver_result(request, result)
        except Exception:
            logger.exception("Timetable solver failed unexpectedly.")
            raise HTTPException(
                status_code=500,
                detail="Timetable solver failed unexpectedly.",
            ) from None

        if result_errors:
            logger.error("Timetable solver produced an invalid result: %s", result_errors)
            raise HTTPException(
                status_code=500,
                detail="Timetable solver produced an invalid result.",
            )
        return result

    return service_app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = ServiceSettings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)