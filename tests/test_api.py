from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from ortools.sat.python import cp_model
import pytest

from config import DEFAULT_CORS_ORIGINS, ServiceSettings
import main
import solver
from models import (
    AcademicSettings,
    Batch,
    BreakTiming,
    Classroom,
    ConstraintSettings,
    Division,
    Faculty,
    GeneratedActivity,
    Laboratory,
    PeriodTiming,
    SolverRequest,
    SolverResult,
    Subject,
)


def _request():
    return SolverRequest(
        settings=AcademicSettings(
            department="CSE",
            academic_year="2026",
            semester="5",
            working_days=["Monday", "Tuesday"],
            periods_per_day=4,
            period_timings=[
                PeriodTiming(period=1, start_time="09:00", end_time="09:50"),
                PeriodTiming(period=2, start_time="09:50", end_time="10:40"),
                PeriodTiming(period=3, start_time="11:00", end_time="11:50"),
                PeriodTiming(period=4, start_time="11:50", end_time="12:40"),
            ],
            breaks=[BreakTiming(name="Break", start_time="10:40", end_time="11:00")],
        ),
        division=Division(id="D1", name="CSE-5A", number_of_students=30, batch_ids=["B1"]),
        batches=[Batch(id="B1", name="Batch 1", division="CSE-5A", number_of_students=30)],
        subjects=[
            Subject(id="S1", name="Algorithms", code="CS501", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["B1"], room_type="THEORY", required_room_capacity=30),
        ],
        faculty=[
            Faculty(id="F1", name="Faculty 1", subject_ids=["S1"], max_workload=8, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4], "Tuesday": [1, 2, 3, 4]}),
        ],
        classrooms=[
            Classroom(id="R1", name="Room 1", room_type="THEORY", capacity=30, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4], "Tuesday": [1, 2, 3, 4]}),
        ],
        laboratories=[
            Laboratory(id="L1", name="Lab 1", lab_type="CSE", capacity=30, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4], "Tuesday": [1, 2, 3, 4]}),
        ],
        constraints=ConstraintSettings(time_limit_seconds=3),
    )


def _payload():
    return _request().model_dump(mode="json")


def test_root_and_health_endpoints():
    client = TestClient(main.app)

    root_response = client.get("/")
    health_response = client.get("/health")

    assert root_response.status_code == 200
    assert root_response.json() == {"message": "Timetable Solver API is running"}
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok", "service": "timetable-solver"}


def test_development_cors_allows_local_frontend_origin():
    client = TestClient(main.app)

    response = client.options(
        "/solve",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_cors_does_not_allow_unconfigured_origin():
    client = TestClient(main.app)

    response = client.options(
        "/solve",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_service_settings_load_environment_values():
    settings = ServiceSettings.from_env(
        {
            "SOLVER_HOST": "0.0.0.0",
            "SOLVER_PORT": "8123",
            "SOLVER_CORS_ORIGINS": "https://frontend.example, http://localhost:3000/",
        }
    )

    assert settings.host == "0.0.0.0"
    assert settings.port == 8123
    assert settings.cors_origins == ("https://frontend.example", "http://localhost:3000")
    assert ServiceSettings.from_env({}).cors_origins == DEFAULT_CORS_ORIGINS


@pytest.mark.parametrize("port", ["0", "65536", "not-a-number"])
def test_service_settings_reject_invalid_port(port):
    with pytest.raises(ValueError, match="SOLVER_PORT"):
        ServiceSettings.from_env({"SOLVER_PORT": port})


class _FixedStatusSolver:
    def __init__(self, status):
        self.status = status
        self.parameters = SimpleNamespace()

    def Solve(self, model):
        return self.status

    def WallTime(self):
        return 0.01


def test_post_solve_returns_typed_result_json_and_openapi_schema():
    client = TestClient(main.app)
    response = client.post("/solve", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OPTIMAL"
    assert body["activities"][0]["subject_id"] == "S1"
    assert body["statistics"]["requested_periods"] == 1
    assert body["statistics"]["scheduled_periods"] == 1
    assert body["statistics"]["solver_time_seconds"] >= 0
    operation = client.get("/openapi.json").json()["paths"]["/solve"]["post"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/SolverResult")


def test_post_solve_rejects_invalid_working_day():
    payload = _payload()
    payload["settings"]["working_days"] = ["Funday"]

    response = TestClient(main.app).post("/solve", json=payload)

    assert response.status_code == 422
    assert "working_days" in str(response.json()["detail"])


def test_post_solve_rejects_invalid_period_timing():
    payload = _payload()
    payload["settings"]["period_timings"][1]["period"] = 1

    response = TestClient(main.app).post("/solve", json=payload)

    assert response.status_code == 422
    assert "period" in str(response.json()["detail"]).lower()


def test_post_solve_rejects_invalid_break_timing():
    payload = _payload()
    payload["settings"]["breaks"][0]["end_time"] = "not-a-time"

    response = TestClient(main.app).post("/solve", json=payload)

    assert response.status_code == 422
    assert "break" in str(response.json()["detail"]).lower()


def test_post_solve_rejects_invalid_weekly_lab_workload():
    payload = _payload()
    payload["subjects"] = [
        {
            **payload["subjects"][0],
            "id": "LAB",
            "activity_type": "LAB",
            "weekly_periods": 3,
            "required_lab_type": "CSE",
            "duration_periods": 2,
        }
    ]
    payload["laboratories"][0]["required_subject_ids"] = ["LAB"]

    response = TestClient(main.app).post("/solve", json=payload)

    assert response.status_code == 422
    assert "weekly_periods" in str(response.json()["detail"])


def test_post_solve_rejects_explicit_non_two_period_lab_duration():
    payload = _payload()
    payload["subjects"][0].update(
        activity_type="LAB",
        weekly_periods=2,
        required_lab_type="CSE",
        duration_periods=1,
    )
    payload["laboratories"][0]["required_subject_ids"] = ["S1"]

    response = TestClient(main.app).post("/solve", json=payload)

    assert response.status_code == 422
    assert "duration_periods" in str(response.json()["detail"])


@pytest.mark.parametrize(
    ("reference_field", "unknown_id"),
    [("faculty_ids", "F404"), ("applicable_batches", "B404")],
)
def test_post_solve_rejects_invalid_subject_references(reference_field, unknown_id):
    payload = _payload()
    payload["subjects"][0][reference_field] = [unknown_id]

    response = TestClient(main.app).post("/solve", json=payload)

    assert response.status_code == 422
    assert unknown_id in str(response.json()["detail"])


@pytest.mark.parametrize(
    ("entity", "field", "unknown_id"),
    [
        ("faculty", "subject_ids", "S404"),
        ("laboratories", "required_subject_ids", "S404"),
        ("laboratories", "eligible_batches", "B404"),
    ],
)
def test_post_solve_rejects_invalid_eligibility_references(entity, field, unknown_id):
    payload = _payload()
    payload[entity][0][field] = [unknown_id]

    response = TestClient(main.app).post("/solve", json=payload)

    assert response.status_code == 422
    assert unknown_id in str(response.json()["detail"])


def test_post_solve_rejects_invalid_existing_resource_reference():
    payload = _payload()
    payload["existing_timetable"] = [
        {"id": "E1", "day": "Monday", "period": 1, "classroom_id": "R404"},
    ]

    response = TestClient(main.app).post("/solve", json=payload)

    assert response.status_code == 422
    assert "R404" in str(response.json()["detail"])


@pytest.mark.parametrize("resource_field", ["classroom_id", "laboratory_id"])
def test_post_solve_rejects_invalid_existing_room_or_lab_reference(resource_field):
    payload = _payload()
    payload["existing_timetable"] = [
        {"id": "E1", "day": "Monday", "period": 1, resource_field: "UNKNOWN-RESOURCE"},
    ]

    response = TestClient(main.app).post("/solve", json=payload)

    assert response.status_code == 422
    assert "UNKNOWN-RESOURCE" in str(response.json()["detail"])


def test_post_solve_reports_infeasible_without_success_shape():
    payload = _payload()
    payload["faculty"][0]["max_workload"] = 0

    response = TestClient(main.app).post("/solve", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "INFEASIBLE"
    assert body["activities"] == []
    assert body["violations"]


def test_post_solve_reports_unknown_as_time_limited_without_activities(monkeypatch):
    monkeypatch.setattr(solver.cp_model, "CpSolver", lambda: _FixedStatusSolver(cp_model.UNKNOWN))

    response = TestClient(main.app).post("/solve", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "TIME_LIMITED"
    assert body["activities"] == []
    assert body["warnings"]


def test_post_solve_does_not_report_model_invalid_as_success(monkeypatch):
    monkeypatch.setattr(solver.cp_model, "CpSolver", lambda: _FixedStatusSolver(cp_model.MODEL_INVALID))

    response = TestClient(main.app).post("/solve", json=_payload())

    assert response.status_code == 500
    assert "FEASIBLE" not in response.text
    assert "MODEL_INVALID" not in response.text


def test_post_solve_sanitizes_unexpected_solver_exception(monkeypatch):
    def fail_solver(request):
        raise RuntimeError("private solver internals")

    monkeypatch.setattr(main, "solve_basic", fail_solver)

    response = TestClient(main.app, raise_server_exceptions=False).post("/solve", json=_payload())

    assert response.status_code == 500
    assert "private solver internals" not in response.text
    assert "Traceback" not in response.text


def test_post_solve_rejects_incomplete_success_result(monkeypatch):
    monkeypatch.setattr(
        main,
        "solve_basic",
        lambda request: SolverResult(status="OPTIMAL", statistics={"requested_periods": 1}),
    )

    response = TestClient(main.app).post("/solve", json=_payload())

    assert response.status_code == 500
    assert response.json()["detail"] == "Timetable solver produced an invalid result."


def test_post_solve_rejects_result_with_unknown_subject(monkeypatch):
    invalid_result = SolverResult(
        status="OPTIMAL",
        activities=[
            GeneratedActivity(
                subject_id="UNKNOWN",
                subject_name="Unknown",
                day="Monday",
                period=1,
                duration_periods=1,
                faculty_id="F1",
                division="CSE-5A",
                batch_ids=["B1"],
                classroom_id="R1",
                activity_type="THEORY",
                activity_mode="WHOLE_DIVISION",
            ),
        ],
        statistics={"requested_periods": 1, "scheduled_periods": 1, "free_periods": 7},
    )
    monkeypatch.setattr(main, "solve_basic", lambda request: invalid_result)

    response = TestClient(main.app).post("/solve", json=_payload())

    assert response.status_code == 500
    assert "UNKNOWN" not in response.text
