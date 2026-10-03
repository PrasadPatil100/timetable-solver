from __future__ import annotations

from collections import Counter
from datetime import datetime
from itertools import combinations

import pytest

from models import (
    AcademicSettings,
    Batch,
    BreakTiming,
    Classroom,
    ConstraintSettings,
    Division,
    ExistingActivity,
    Faculty,
    Laboratory,
    PeriodTiming,
    SolverRequest,
    Subject,
)
from solver import solve_basic


COLLEGE_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
PERIODS_PER_DAY = 6


def _time_minutes(value: str) -> int:
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def _college_request(subjects, days=None, room_count=4, lab_count=2):
    working_days = days or COLLEGE_DAYS
    timings = [
        PeriodTiming(period=1, start_time="09:00", end_time="09:50"),
        PeriodTiming(period=2, start_time="09:50", end_time="10:40"),
        PeriodTiming(period=3, start_time="11:00", end_time="11:50"),
        PeriodTiming(period=4, start_time="11:50", end_time="12:40"),
        PeriodTiming(period=5, start_time="13:30", end_time="14:20"),
        PeriodTiming(period=6, start_time="14:20", end_time="15:10"),
    ]
    period_ids = list(range(1, PERIODS_PER_DAY + 1))
    availability = {day: list(period_ids) for day in working_days}
    return SolverRequest(
        settings=AcademicSettings(
            department="CSE",
            academic_year="2026",
            semester="5",
            working_days=working_days,
            periods_per_day=PERIODS_PER_DAY,
            period_timings=timings,
            breaks=[
                BreakTiming(name="Morning break", start_time="10:40", end_time="11:00"),
                BreakTiming(name="Lunch", start_time="12:40", end_time="13:30"),
            ],
        ),
        division=Division(
            id="DIV-CSE-5A",
            name="CSE-5A",
            number_of_students=60,
            batch_ids=["TB1", "TB2", "TB3"],
        ),
        batches=[
            Batch(id="TB1", name="Batch 1", division="CSE-5A", number_of_students=20),
            Batch(id="TB2", name="Batch 2", division="CSE-5A", number_of_students=20),
            Batch(id="TB3", name="Batch 3", division="CSE-5A", number_of_students=20),
        ],
        subjects=list(subjects),
        faculty=[
            Faculty(id=f"F{index}", name=f"Faculty {index}", max_workload=24, available_days=list(working_days), available_periods=availability)
            for index in range(1, 7)
        ],
        classrooms=[
            Classroom(
                id=f"R{index}",
                name=f"Classroom {index}",
                room_type="THEORY",
                capacity=60,
                available_days=list(working_days),
                available_periods={day: list(period_ids) for day in working_days},
            )
            for index in range(1, room_count + 1)
        ],
        laboratories=[
            Laboratory(
                id=f"L{index}",
                name=f"CSE Lab {index}",
                lab_type="CSE",
                capacity=60,
                available_days=list(working_days),
                available_periods={day: list(period_ids) for day in working_days},
            )
            for index in range(1, lab_count + 1)
        ],
        constraints=ConstraintSettings(time_limit_seconds=8),
    )


def _activity_periods(activity):
    return set(range(activity.period, activity.period + activity.duration_periods))


def _overlaps_break(request, activity) -> bool:
    period_timings = {timing.period: timing for timing in request.settings.period_timings}
    first_timing = period_timings[activity.period]
    last_timing = period_timings[activity.period + activity.duration_periods - 1]
    start = _time_minutes(first_timing.start_time)
    end = _time_minutes(last_timing.end_time)
    return any(
        start < _time_minutes(break_timing.end_time)
        and _time_minutes(break_timing.start_time) < end
        for break_timing in request.settings.breaks
    )


def _assert_valid_result(request, result):
    assert result.status in {"OPTIMAL", "FEASIBLE"}
    assert result.solve_time_seconds >= 0
    assert result.statistics.solver_time_seconds >= 0
    assert result.statistics.requested_periods > 0
    assert result.statistics.scheduled_periods == sum(activity.duration_periods for activity in result.activities)

    subject_by_id = {subject.id: subject for subject in request.subjects}
    faculty_ids = {faculty.id for faculty in request.faculty}
    classroom_ids = {room.id for room in request.classrooms}
    laboratory_ids = {lab.id for lab in request.laboratories}
    day_names = set(request.settings.working_days)

    actual_counts = Counter()
    faculty_workloads = Counter()
    occupied_resource_slots = {"faculty": set(), "classroom": set(), "laboratory": set(), "batch": set()}

    for activity in result.activities:
        subject = subject_by_id[activity.subject_id]
        assert activity.day in day_names
        assert 1 <= activity.period <= request.settings.periods_per_day
        assert activity.period + activity.duration_periods - 1 <= request.settings.periods_per_day
        assert activity.faculty_id in faculty_ids
        assert activity.division == request.division.name
        assert activity.activity_mode == subject.activity_mode
        assert activity.activity_type == subject.activity_type
        assert activity.duration_periods == (2 if subject.activity_type == "LAB" else 1)
        assert set(activity.batch_ids).issubset(set(subject.applicable_batches or request.division.batch_ids))
        assert not _overlaps_break(request, activity)

        if activity.activity_type == "LAB":
            assert activity.laboratory_id in laboratory_ids
            assert activity.classroom_id is None
        else:
            assert activity.classroom_id in classroom_ids
            assert activity.laboratory_id is None

        unit = "division" if subject.activity_mode == "WHOLE_DIVISION" else activity.batch_ids[0]
        actual_counts[(subject.id, unit)] += 1
        faculty_workloads[activity.faculty_id] += activity.duration_periods

        for period in _activity_periods(activity):
            faculty_slot = (activity.faculty_id, activity.day, period)
            assert faculty_slot not in occupied_resource_slots["faculty"]
            occupied_resource_slots["faculty"].add(faculty_slot)

            resource_type = "laboratory" if activity.activity_type == "LAB" else "classroom"
            resource_id = activity.laboratory_id if resource_type == "laboratory" else activity.classroom_id
            resource_slot = (resource_id, activity.day, period)
            assert resource_slot not in occupied_resource_slots[resource_type]
            occupied_resource_slots[resource_type].add(resource_slot)

            for batch_id in activity.batch_ids:
                batch_slot = (batch_id, activity.day, period)
                assert batch_slot not in occupied_resource_slots["batch"]
                occupied_resource_slots["batch"].add(batch_slot)

    for subject in request.subjects:
        occurrence_count = subject.weekly_periods // (2 if subject.activity_type == "LAB" else 1)
        units = ["division"] if subject.activity_mode == "WHOLE_DIVISION" else (subject.applicable_batches or request.division.batch_ids)
        for unit in units:
            assert actual_counts[(subject.id, unit)] == occurrence_count

    for faculty in request.faculty:
        fixed_load = sum(
            activity.duration_periods
            for activity in request.existing_timetable
            if activity.fixed and activity.faculty_id == faculty.id
        )
        assert fixed_load + faculty_workloads[faculty.id] <= faculty.max_workload

    for activity in result.activities:
        periods = _activity_periods(activity)
        for fixed in request.existing_timetable:
            if not fixed.fixed or activity.day != fixed.day or not periods.intersection(_activity_periods(fixed)):
                continue
            assert not (fixed.faculty_id and activity.faculty_id == fixed.faculty_id)
            assert not (fixed.classroom_id and activity.classroom_id == fixed.classroom_id)
            assert not (fixed.laboratory_id and activity.laboratory_id == fixed.laboratory_id)
            assert not (fixed.division in {request.division.id, request.division.name})
            assert not set(fixed.batch_ids).intersection(activity.batch_ids)

    for left, right in combinations(result.activities, 2):
        if left.day != right.day or not _activity_periods(left).intersection(_activity_periods(right)):
            continue
        assert not (left.activity_mode == "WHOLE_DIVISION" or right.activity_mode == "WHOLE_DIVISION")

    occupied_division_slots = {
        (activity.day, period)
        for activity in result.activities
        for period in _activity_periods(activity)
    }
    occupied_division_slots.update(
        (activity.day, period)
        for activity in request.existing_timetable
        if activity.fixed
        for period in _activity_periods(activity)
    )
    timetable_capacity = len(request.settings.working_days) * request.settings.periods_per_day
    assert result.statistics.free_periods == max(0, timetable_capacity - len(occupied_division_slots))


def test_end_to_end_normal_six_day_theory_timetable():
    subjects = [
        Subject(id="ALG", name="Algorithms", code="CS501", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=3, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
        Subject(id="DB", name="Databases", code="CS502", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=3, faculty_ids=["F2"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
        Subject(id="OS", name="Operating Systems", code="CS503", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=3, faculty_ids=["F3"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
        Subject(id="NET", name="Networks", code="CS504", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=3, faculty_ids=["F4"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    request = _college_request(subjects)

    result = solve_basic(request)

    _assert_valid_result(request, result)
    assert {activity.day for activity in result.activities}.issubset(set(COLLEGE_DAYS))
    assert len(result.activities) == 12
    assert result.statistics.requested_periods == 12
    assert result.statistics.free_periods > 0


def test_end_to_end_theory_and_two_period_labs():
    subjects = [
        Subject(id="THEORY", name="Theory", code="CS510", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
        Subject(id="LAB", name="Practical Lab", code="CS511", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=4, faculty_ids=["F2"], applicable_batches=["TB1", "TB2", "TB3"], required_lab_type="CSE", required_room_capacity=60),
    ]
    request = _college_request(subjects)
    request.laboratories[0].required_subject_ids = ["LAB"]

    result = solve_basic(request)

    _assert_valid_result(request, result)
    labs = [activity for activity in result.activities if activity.subject_id == "LAB"]
    assert len(labs) == 2
    assert all(activity.duration_periods == 2 for activity in labs)
    assert result.statistics.requested_periods == result.statistics.scheduled_periods == 6


def test_end_to_end_parallel_rotation_and_whole_division_modes():
    subjects = [
        Subject(id="PAR", name="Parallel Workshop", code="CS520", activity_type="THEORY", activity_mode="PARALLEL_BATCH", weekly_periods=1, faculty_ids=["F1", "F2", "F3"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=20),
        Subject(id="ROT1", name="Rotation 1", code="CS521A", activity_type="THEORY", activity_mode="ROTATIONAL_BATCH", weekly_periods=1, faculty_ids=["F1"], activity_group_id="ROT-520", applicable_batches=["TB1"], room_type="THEORY", required_room_capacity=20),
        Subject(id="ROT2", name="Rotation 2", code="CS521B", activity_type="THEORY", activity_mode="ROTATIONAL_BATCH", weekly_periods=1, faculty_ids=["F2"], activity_group_id="ROT-520", applicable_batches=["TB2"], room_type="THEORY", required_room_capacity=20),
        Subject(id="ROT3", name="Rotation 3", code="CS521C", activity_type="THEORY", activity_mode="ROTATIONAL_BATCH", weekly_periods=1, faculty_ids=["F3"], activity_group_id="ROT-520", applicable_batches=["TB3"], room_type="THEORY", required_room_capacity=20),
        Subject(id="WHOLE", name="Whole Division Seminar", code="CS522", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F4"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    request = _college_request(subjects)

    result = solve_basic(request)

    _assert_valid_result(request, result)
    parallel = [activity for activity in result.activities if activity.subject_id == "PAR"]
    assert len(parallel) == 3
    assert {tuple(activity.batch_ids) for activity in parallel} == {("TB1",), ("TB2",), ("TB3",)}
    assert len({(activity.day, activity.period) for activity in parallel}) == 1
    assert len({activity.faculty_id for activity in parallel}) == 3
    assert len({activity.classroom_id for activity in parallel}) == 3

    rotation = [activity for activity in result.activities if activity.subject_id.startswith("ROT")]
    assert len(rotation) == 3
    assert len({(activity.day, activity.period) for activity in rotation}) == 1
    assert {tuple(activity.batch_ids) for activity in rotation} == {("TB1",), ("TB2",), ("TB3",)}
    whole = next(activity for activity in result.activities if activity.subject_id == "WHOLE")
    assert all(
        activity.day != whole.day or not _activity_periods(activity).intersection(_activity_periods(whole))
        for activity in result.activities
        if activity is not whole
    )


def test_end_to_end_existing_fixed_resources_batches_and_division_are_preserved():
    subjects = [
        Subject(id="THEORY", name="Fixed-aware Theory", code="CS530", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
        Subject(id="BATCH", name="Fixed-aware Batch", code="CS531", activity_type="THEORY", activity_mode="PARALLEL_BATCH", weekly_periods=1, faculty_ids=["F2"], applicable_batches=["TB2"], room_type="THEORY", required_room_capacity=20),
        Subject(id="LAB", name="Fixed-aware Lab", code="CS532", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F3"], applicable_batches=["TB1", "TB2", "TB3"], required_lab_type="CSE", required_room_capacity=60),
    ]
    request = _college_request(subjects, days=COLLEGE_DAYS[:5], room_count=1, lab_count=1)
    request.laboratories[0].required_subject_ids = ["LAB"]
    request.existing_timetable = [
        ExistingActivity(id="FIXED-FACULTY", day="Monday", period=1, faculty_id="F1"),
        ExistingActivity(id="FIXED-ROOM", day="Tuesday", period=1, classroom_id="R1"),
        ExistingActivity(id="FIXED-LAB", day="Wednesday", period=3, laboratory_id="L1", duration_periods=2),
        ExistingActivity(id="FIXED-DIVISION", day="Thursday", period=1, division=request.division.id),
        ExistingActivity(id="FIXED-BATCH", day="Friday", period=1, batch_ids=["TB2"]),
    ]

    result = solve_basic(request)

    _assert_valid_result(request, result)
    assert len(result.activities) == 4
    assert all(activity.day in COLLEGE_DAYS[:5] for activity in result.activities)


def test_end_to_end_faculty_unavailability_is_respected():
    subject = Subject(
        id="UNAVAILABLE-FACULTY",
        name="Unavailable Faculty",
        code="CS540",
        activity_type="THEORY",
        activity_mode="WHOLE_DIVISION",
        weekly_periods=1,
        faculty_ids=["F1"],
        applicable_batches=["TB1", "TB2", "TB3"],
        room_type="THEORY",
        required_room_capacity=60,
    )
    request = _college_request([subject], days=["Monday"], room_count=1)
    request.faculty[0].available_periods = {"Monday": [1, 2, 3]}
    request.faculty[0].unavailable_slots = ["Monday:1", "Monday:2"]
    request.classrooms[0].available_periods = {"Monday": [1, 2, 3]}

    result = solve_basic(request)

    _assert_valid_result(request, result)
    assert len(result.activities) == 1
    assert result.activities[0].period == 3


def test_end_to_end_classroom_and_lab_availability_are_respected():
    subjects = [
        Subject(id="ROOM", name="Room Availability", code="CS550", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
        Subject(id="LAB", name="Lab Availability", code="CS551", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F2"], applicable_batches=["TB1", "TB2", "TB3"], required_lab_type="CSE", required_room_capacity=60),
    ]
    request = _college_request(subjects, days=["Monday", "Tuesday"], room_count=1, lab_count=1)
    request.classrooms[0].available_days = ["Monday"]
    request.classrooms[0].available_periods = {"Monday": [2]}
    request.laboratories[0].required_subject_ids = ["LAB"]
    request.laboratories[0].available_days = ["Tuesday"]
    request.laboratories[0].available_periods = {"Tuesday": [3, 4]}

    result = solve_basic(request)

    _assert_valid_result(request, result)
    room_activity = next(activity for activity in result.activities if activity.subject_id == "ROOM")
    lab_activity = next(activity for activity in result.activities if activity.subject_id == "LAB")
    assert (room_activity.day, room_activity.period, room_activity.classroom_id) == ("Monday", 2, "R1")
    assert (lab_activity.day, lab_activity.period, lab_activity.duration_periods, lab_activity.laboratory_id) == ("Tuesday", 3, 2, "L1")


def test_end_to_end_impossible_workload_returns_infeasible_without_activities():
    subject = Subject(
        id="IMPOSSIBLE",
        name="Impossible Workload",
        code="CS560",
        activity_type="THEORY",
        activity_mode="WHOLE_DIVISION",
        weekly_periods=1,
        faculty_ids=["F1"],
        applicable_batches=["TB1", "TB2", "TB3"],
        room_type="THEORY",
        required_room_capacity=60,
    )
    request = _college_request([subject], days=["Monday"], room_count=1)
    request.faculty[0].max_workload = 0

    result = solve_basic(request)

    assert result.status == "INFEASIBLE"
    assert result.activities == []
    assert result.violations
    assert result.statistics.requested_periods == 1
