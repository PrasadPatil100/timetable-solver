from __future__ import annotations

from time import perf_counter

import pytest

from models import (
    AcademicSettings,
    Batch,
    Classroom,
    ConstraintSettings,
    Division,
    Faculty,
    PeriodTiming,
    SolverRequest,
    Subject,
)
from solver import solve_basic


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _request(subject_count: int, day_count: int, periods_per_day: int, time_limit_seconds: int) -> SolverRequest:
    days = DAYS[:day_count]
    timings = [
        PeriodTiming(
            period=period,
            start_time=f"{8 + (period - 1) * 1}:00",
            end_time=f"{8 + (period - 1) * 1}:50",
        )
        for period in range(1, periods_per_day + 1)
    ]
    periods = list(range(1, periods_per_day + 1))
    available = {day: periods for day in days}
    subjects = [
        Subject(
            id=f"SUBJECT-{index + 1}",
            name=f"Theory {index + 1}",
            code=f"CS{600 + index}",
            activity_type="THEORY",
            activity_mode="WHOLE_DIVISION",
            weekly_periods=2,
            faculty_ids=[f"F{index % 4 + 1}"],
            applicable_batches=["B1"],
            room_type="THEORY",
            required_room_capacity=40,
        )
        for index in range(subject_count)
    ]
    return SolverRequest(
        settings=AcademicSettings(
            department="CSE",
            academic_year="2026",
            semester="6",
            working_days=days,
            periods_per_day=periods_per_day,
            period_timings=timings,
        ),
        division=Division(id="D1", name="CSE-6A", number_of_students=40, batch_ids=["B1"]),
        batches=[Batch(id="B1", name="Batch 1", division="CSE-6A", number_of_students=40)],
        subjects=subjects,
        faculty=[
            Faculty(
                id=f"F{index}",
                name=f"Faculty {index}",
                max_workload=20,
                available_days=days,
                available_periods=available,
            )
            for index in range(1, 5)
        ],
        classrooms=[
            Classroom(
                id=f"R{index}",
                name=f"Room {index}",
                room_type="THEORY",
                capacity=50,
                available_days=days,
                available_periods=available,
            )
            for index in range(1, 3)
        ],
        constraints=ConstraintSettings(time_limit_seconds=time_limit_seconds),
    )


@pytest.mark.parametrize(
    ("size", "subject_count", "day_count", "periods_per_day", "time_limit_seconds"),
    [
        ("small", 1, 3, 4, 5),
        ("medium", 4, 5, 5, 5),
        ("larger", 8, 6, 6, 8),
    ],
    ids=["small", "medium", "larger"],
)
def test_solver_performance_profile(size, subject_count, day_count, periods_per_day, time_limit_seconds, record_property):
    request = _request(subject_count, day_count, periods_per_day, time_limit_seconds)

    started = perf_counter()
    result = solve_basic(request)
    wall_seconds = perf_counter() - started

    record_property(f"{size}_wall_seconds", wall_seconds)
    record_property(f"{size}_solver_seconds", result.solve_time_seconds)
    print(
        f"PERF size={size} wall_seconds={wall_seconds:.3f} "
        f"solver_seconds={result.solve_time_seconds:.3f} status={result.status}"
    )

    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    assert result.solve_time_seconds >= 0
    assert result.solve_time_seconds <= time_limit_seconds + 1
    assert result.statistics.requested_periods == subject_count * 2
    if result.status in {"OPTIMAL", "FEASIBLE"}:
        assert len(result.activities) == subject_count * 2
        assert result.statistics.scheduled_periods == subject_count * 2
    else:
        assert result.activities == []
