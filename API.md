# Timetable Solver API

Standalone FastAPI service. The service does not connect to the main application or a database.

## Endpoints

### `GET /`

Returns a simple running message:

```json
{"message":"Timetable Solver API is running"}
```

### `GET /health`

Returns a minimal health response:

```json
{"status":"ok","service":"timetable-solver"}
```

### `POST /solve`

Accepts a JSON `SolverRequest` and returns a JSON `SolverResult`.

Headers:

```text
Content-Type: application/json
```

A minimal request example (all referenced IDs must be internally consistent):

```json
{
  "settings": {
    "department": "CSE",
    "academic_year": "2026",
    "semester": "5",
    "working_days": ["Monday", "Tuesday"],
    "periods_per_day": 2,
    "period_timings": [
      {"period": 1, "start_time": "09:00", "end_time": "09:50"},
      {"period": 2, "start_time": "10:00", "end_time": "10:50"}
    ],
    "breaks": []
  },
  "division": {
    "id": "D1",
    "name": "CSE-5A",
    "number_of_students": 30,
    "batch_ids": ["B1"]
  },
  "batches": [
    {"id": "B1", "name": "Batch 1", "division": "CSE-5A", "number_of_students": 30}
  ],
  "subjects": [
    {
      "id": "S1",
      "name": "Algorithms",
      "code": "CS501",
      "activity_type": "THEORY",
      "activity_mode": "WHOLE_DIVISION",
      "weekly_periods": 1,
      "faculty_ids": ["F1"],
      "applicable_batches": ["B1"],
      "room_type": "THEORY",
      "required_room_capacity": 30
    }
  ],
  "faculty": [
    {
      "id": "F1",
      "name": "Faculty 1",
      "subject_ids": ["S1"],
      "max_workload": 8,
      "available_days": ["Monday", "Tuesday"],
      "available_periods": {"Monday": [1, 2], "Tuesday": [1, 2]},
      "unavailable_slots": []
    }
  ],
  "classrooms": [
    {
      "id": "R1",
      "name": "Room 1",
      "room_type": "THEORY",
      "capacity": 30,
      "available_days": ["Monday", "Tuesday"],
      "available_periods": {"Monday": [1, 2], "Tuesday": [1, 2]}
    }
  ],
  "laboratories": [],
  "existing_timetable": [],
  "constraints": {"time_limit_seconds": 3}
}
```

Example call from local development:

```bash
curl -X POST http://127.0.0.1:8000/solve \
  -H "Content-Type: application/json" \
  --data-binary @request.json
```

A successful response uses the existing `SolverResult` model. Fields include `status`, `solve_time_seconds`, `activities`, `warnings`, `violations`, and `statistics`. Each generated activity includes subject, day, starting period, duration, faculty, division, batch IDs, classroom/laboratory IDs, activity type, and activity mode.

Example successful response:

```json
{
  "status": "OPTIMAL",
  "solve_time_seconds": 0.01,
  "activities": [
    {
      "subject_id": "S1",
      "subject_name": "Algorithms",
      "day": "Monday",
      "period": 1,
      "duration_periods": 1,
      "faculty_id": "F1",
      "division": "CSE-5A",
      "batch_ids": ["B1"],
      "classroom_id": "R1",
      "laboratory_id": null,
      "activity_type": "THEORY",
      "activity_mode": "WHOLE_DIVISION"
    }
  ],
  "warnings": [],
  "violations": [],
  "statistics": {
    "requested_periods": 1,
    "scheduled_periods": 1,
    "free_periods": 3,
    "solver_time_seconds": 0.01
  }
}
```

Proven infeasibility is returned with HTTP 200 and `status: "INFEASIBLE"`, an empty activities list, and a violation message. This is a solver outcome, not an HTTP request error:

```json
{
  "status": "INFEASIBLE",
  "solve_time_seconds": 0.01,
  "activities": [],
  "warnings": ["No feasible timetable could be constructed under the hard constraints."],
  "violations": ["No feasible timetable under the provided constraints."],
  "statistics": {
    "requested_periods": 1,
    "scheduled_periods": 0,
    "free_periods": 4,
    "solver_time_seconds": 0.01
  }
}
```

Supported result statuses are `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, and `TIME_LIMITED`. `TIME_LIMITED` means CP-SAT returned `UNKNOWN` without a feasible incumbent; its activity list is empty. It is not a successful timetable. A malformed request returns HTTP 422. Unexpected solver failures or invalid solver output return a generic HTTP 500 response without internal details.

## Node.js Call Contract

```text
Node.js
  -> HTTP POST
Python FastAPI /solve
  -> OR-Tools CP-SAT
  -> SolverResult JSON
  -> Node.js
  -> React
```

The future Node.js backend should send `POST {SOLVER_URL}/solve`, set `Content-Type: application/json`, and send the existing `SolverRequest` JSON object. It should parse the `SolverResult` response body and branch on `status`; only `OPTIMAL` and `FEASIBLE` contain validated generated timetables. Treat `INFEASIBLE` and `TIME_LIMITED` as non-successful scheduling outcomes. Treat HTTP 422 as invalid input, HTTP 500 as a service failure, and handle network timeouts separately. The React application should continue communicating with its backend rather than calling this service directly.

## Configuration and Running

Install runtime dependencies with `pip install -r requirements.txt`. For tests, use `pip install -r requirements-test.txt`.

Run locally with `uvicorn main:app --host 127.0.0.1 --port 8000` or `python main.py`.

Environment variables:

- `SOLVER_HOST`: bind host for `python main.py`; default `127.0.0.1`.
- `SOLVER_PORT`: bind port for `python main.py`; default `8000`.
- `SOLVER_CORS_ORIGINS`: comma-separated browser origins; default allows localhost and 127.0.0.1 on ports 3000 and 5173.

The request's `constraints.time_limit_seconds` remains the solver time limit (default 3 seconds in the current request model). It is not silently overridden by service configuration. CORS is for browser-origin access during development; it is not an access-control mechanism for Node.js server-to-server requests.
