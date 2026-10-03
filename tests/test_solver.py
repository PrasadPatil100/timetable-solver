import pytest
from ortools.sat.python import cp_model

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
from solver import _add_constraints, _resource_available, solve_basic


@pytest.fixture
def basic_request():
    settings = AcademicSettings(
        department="CSE",
        academic_year="2025",
        semester="6",
        working_days=["Monday", "Tuesday"],
        periods_per_day=6,
        period_timings=[
            PeriodTiming(period=1, start_time="09:00", end_time="09:50"),
            PeriodTiming(period=2, start_time="09:50", end_time="10:40"),
            PeriodTiming(period=3, start_time="11:00", end_time="11:50"),
            PeriodTiming(period=4, start_time="11:50", end_time="12:40"),
            PeriodTiming(period=5, start_time="13:30", end_time="14:20"),
            PeriodTiming(period=6, start_time="14:20", end_time="15:10"),
        ],
        breaks=[
            BreakTiming(name="Lunch", start_time="10:40", end_time="11:00"),
        ],
    )
    division = Division(id="D1", name="TY CSE B", number_of_students=60, batch_ids=["TB1", "TB2", "TB3"])
    batches = [
        Batch(id="TB1", name="TB1", division="TY CSE B", number_of_students=20),
        Batch(id="TB2", name="TB2", division="TY CSE B", number_of_students=20),
        Batch(id="TB3", name="TB3", division="TY CSE B", number_of_students=20),
    ]
    faculty = [
        Faculty(id="F1", name="Faculty 1", subject_ids=[], qualification="MTech", max_workload=8, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4, 5, 6], "Tuesday": [1, 2, 3, 4, 5, 6]}),
        Faculty(id="F2", name="Faculty 2", subject_ids=[], qualification="MTech", max_workload=8, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4, 5, 6], "Tuesday": [1, 2, 3, 4, 5, 6]}),
        Faculty(id="F3", name="Faculty 3", subject_ids=[], qualification="MTech", max_workload=6, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4, 5, 6], "Tuesday": [1, 2, 3, 4, 5, 6]}),
    ]
    classrooms = [
        Classroom(id="R1", name="Room 1", room_type="THEORY", capacity=60, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4, 5, 6], "Tuesday": [1, 2, 3, 4, 5, 6]}),
        Classroom(id="R2", name="Room 2", room_type="THEORY", capacity=60, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4, 5, 6], "Tuesday": [1, 2, 3, 4, 5, 6]}),
        Classroom(id="R3", name="Room 3", room_type="THEORY", capacity=60, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4, 5, 6], "Tuesday": [1, 2, 3, 4, 5, 6]}),
    ]
    labs = [
        Laboratory(id="L1", name="Lab 1", lab_type="CSE", capacity=40, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4, 5, 6], "Tuesday": [1, 2, 3, 4, 5, 6]}, required_subject_ids=["LAB1"], eligible_batches=["TB1", "TB2", "TB3"], resources=["PC"]),
    ]
    return SolverRequest(
        settings=settings,
        division=division,
        batches=batches,
        subjects=[
            Subject(id="DAA", name="DAA", code="CS101", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
            Subject(id="ADE", name="ADE", code="CS102", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F2"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
            Subject(id="GATE", name="GATE", code="CS103", activity_type="ACTIVITY", activity_mode="PARALLEL_BATCH", weekly_periods=2, faculty_ids=["F1", "F2", "F3"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
            Subject(id="NPR", name="NPR", code="CS104", activity_type="THEORY", activity_mode="ROTATIONAL_BATCH", weekly_periods=2, faculty_ids=["F1", "F2", "F3"], activity_group_id="NPR-ROTATION", applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
            Subject(id="LAB1", name="Lab 1", code="CS105", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], duration_periods=2, required_lab_type="CSE", room_type="THEORY", required_room_capacity=40),
        ],
        faculty=faculty,
        classrooms=classrooms,
        laboratories=labs,
        constraints=ConstraintSettings(time_limit_seconds=3),
    )


def test_basic_theory_scheduling(basic_request):
    result = solve_basic(basic_request)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    assert result.statistics.requested_periods > 0
    assert result.statistics.scheduled_periods >= 0
    assert all(activity.batch_ids == ["TB1", "TB2", "TB3"] for activity in result.activities if activity.activity_mode == "WHOLE_DIVISION")


def test_faculty_clash(basic_request):
    req = basic_request.model_copy(deep=True)
    req.subjects = [
        Subject(id="SUB1", name="T1", code="T1", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
        Subject(id="SUB2", name="T2", code="T2", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    faculty_slots = {}
    for activity in result.activities:
        for period in range(activity.period, activity.period + activity.duration_periods):
            key = (activity.day, period, activity.faculty_id)
            faculty_slots.setdefault(key, 0)
            faculty_slots[key] += 1
    assert all(count <= 1 for count in faculty_slots.values())


def test_classroom_clash(basic_request):
    req = basic_request.model_copy(deep=True)
    req.classrooms = [
        Classroom(id="R1", name="Room 1", room_type="THEORY", capacity=60, available_days=["Monday"], available_periods={"Monday": [1, 2, 3, 4, 5, 6]})
    ]
    req.subjects = [
        Subject(id="S1", name="S1", code="S1", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
        Subject(id="S2", name="S2", code="S2", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F2"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    room_slots = {}
    for activity in result.activities:
        for period in range(activity.period, activity.period + activity.duration_periods):
            key = (activity.day, period, activity.classroom_id)
            room_slots.setdefault(key, 0)
            room_slots[key] += 1
    assert all(count <= 1 for count in room_slots.values())


def test_laboratory_clash(basic_request):
    req = basic_request.model_copy(deep=True)
    req.laboratories = [
        Laboratory(id="L1", name="Lab 1", lab_type="CSE", capacity=40, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4, 5, 6], "Tuesday": [1, 2, 3, 4, 5, 6]}, required_subject_ids=["LABA", "LABB"], eligible_batches=["TB1", "TB2", "TB3"], resources=["PC"]),
    ]
    req.subjects = [
            Subject(id="LABA", name="Labs A", code="LA", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], duration_periods=2, required_lab_type="CSE", room_type="THEORY", required_room_capacity=40),
            Subject(id="LABB", name="Labs B", code="LB", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F2"], applicable_batches=["TB1", "TB2", "TB3"], duration_periods=2, required_lab_type="CSE", room_type="THEORY", required_room_capacity=40),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    assert sum(activity.subject_id == "LABA" for activity in result.activities) == 1
    assert sum(activity.subject_id == "LABB" for activity in result.activities) == 1
    lab_slots = {}
    for activity in result.activities:
        if activity.laboratory_id:
            for period in range(activity.period, activity.period + activity.duration_periods):
                key = (activity.day, period, activity.laboratory_id)
                lab_slots.setdefault(key, 0)
                lab_slots[key] += 1
    assert all(count <= 1 for count in lab_slots.values())


def test_existing_timetable_protection(basic_request):
    req = basic_request.model_copy(deep=True)
    req.subjects = [
        Subject(id="DAA", name="DAA", code="CS101", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    req.existing_timetable = [
        ExistingActivity(id="E1", day="Monday", period=1, duration_periods=1, subject_id="DAA", faculty_id="F1", division="TY CSE B", batch_ids=["TB1", "TB2", "TB3"], classroom_id="R1", fixed=True),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    fixed = req.existing_timetable[0]
    for activity in result.activities:
        if activity.day != fixed.day:
            continue
        generated_periods = set(range(activity.period, activity.period + activity.duration_periods))
        fixed_periods = set(range(fixed.period, fixed.period + fixed.duration_periods))
        assert not generated_periods.intersection(fixed_periods)


def test_batch_clash(basic_request):
    req = basic_request.model_copy(deep=True)
    req.subjects = [
        Subject(id="A1", name="A1", code="A1", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
        Subject(id="A2", name="A2", code="A2", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F2"], applicable_batches=["TB1"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    batch_usage = {}
    for activity in result.activities:
        for b in activity.batch_ids:
            key = (activity.day, activity.period, b)
            batch_usage.setdefault(key, 0)
            batch_usage[key] += 1
    assert all(v <= 1 for v in batch_usage.values())


def test_whole_division_occupancy(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday"]
    for faculty in req.faculty:
        faculty.available_days = ["Monday"]
        faculty.available_periods = {"Monday": [1]}
    for room in req.classrooms:
        room.available_days = ["Monday"]
        room.available_periods = {"Monday": [1]}
    req.subjects = [
        Subject(id="WD1", name="Whole Div", code="WD1", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
        Subject(id="WD2", name="Batch activity", code="WD2", activity_type="THEORY", activity_mode="PARALLEL_BATCH", weekly_periods=1, faculty_ids=["F2"], applicable_batches=["TB1"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status == "INFEASIBLE"


def test_parallel_batches(basic_request):
    req = basic_request.model_copy(deep=True)
    req.classrooms.append(Classroom(id="R4", name="Room 4", room_type="THEORY", capacity=60, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4, 5, 6], "Tuesday": [1, 2, 3, 4, 5, 6]}))
    req.subjects = [
        Subject(id="PAR", name="Parallel", code="PAR", activity_type="THEORY", activity_mode="PARALLEL_BATCH", weekly_periods=1, faculty_ids=["F1", "F2", "F3"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    parallel = [activity for activity in result.activities if activity.activity_mode == "PARALLEL_BATCH"]
    assert len(parallel) == 3
    assert {tuple(activity.batch_ids) for activity in parallel} == {("TB1",), ("TB2",), ("TB3",)}
    assert len({(activity.day, activity.period) for activity in parallel}) == 1
    assert len({activity.faculty_id for activity in parallel}) == 3
    assert len({activity.classroom_id for activity in parallel}) == 3


def test_rotational_batches(basic_request):
    req = basic_request.model_copy(deep=True)
    req.classrooms.append(Classroom(id="R4", name="Room 4", room_type="THEORY", capacity=60, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4, 5, 6], "Tuesday": [1, 2, 3, 4, 5, 6]}))
    req.subjects = [
        Subject(id="ROT1", name="Rotation 1", code="ROT1", activity_type="THEORY", activity_mode="ROTATIONAL_BATCH", weekly_periods=1, faculty_ids=["F1"], activity_group_id="ROT-GROUP", applicable_batches=["TB1"], room_type="THEORY", required_room_capacity=60),
        Subject(id="ROT2", name="Rotation 2", code="ROT2", activity_type="THEORY", activity_mode="ROTATIONAL_BATCH", weekly_periods=1, faculty_ids=["F2"], activity_group_id="ROT-GROUP", applicable_batches=["TB2"], room_type="THEORY", required_room_capacity=60),
        Subject(id="ROT3", name="Rotation 3", code="ROT3", activity_type="THEORY", activity_mode="ROTATIONAL_BATCH", weekly_periods=1, faculty_ids=["F3"], activity_group_id="ROT-GROUP", applicable_batches=["TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    rotation = [activity for activity in result.activities if activity.activity_mode == "ROTATIONAL_BATCH"]
    assert {activity.subject_id for activity in rotation} == {"ROT1", "ROT2", "ROT3"}
    assert {tuple(activity.batch_ids) for activity in rotation} == {("TB1",), ("TB2",), ("TB3",)}
    assert len({(activity.day, activity.period) for activity in rotation}) == 1


def test_rotation_occupies_division_slot(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday"]
    for faculty in req.faculty:
        faculty.available_days = ["Monday"]
        faculty.available_periods = {"Monday": [1]}
    for room in req.classrooms:
        room.available_days = ["Monday"]
        room.available_periods = {"Monday": [1]}
    req.subjects = [
        Subject(id="R1", name="Rotation one", code="R1", activity_type="THEORY", activity_mode="ROTATIONAL_BATCH", weekly_periods=1, faculty_ids=["F1"], activity_group_id="ROT", applicable_batches=["TB1"], room_type="THEORY", required_room_capacity=60),
        Subject(id="R2", name="Rotation two", code="R2", activity_type="THEORY", activity_mode="ROTATIONAL_BATCH", weekly_periods=1, faculty_ids=["F2"], activity_group_id="ROT", applicable_batches=["TB2"], room_type="THEORY", required_room_capacity=60),
        Subject(id="OTHER", name="Other batch", code="OTHER", activity_type="THEORY", activity_mode="PARALLEL_BATCH", weekly_periods=1, faculty_ids=["F3"], applicable_batches=["TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    assert solve_basic(req).status == "INFEASIBLE"


def test_two_period_lab(basic_request):
    req = basic_request.model_copy(deep=True)
    req.subjects = [
        Subject(id="LAB2", name="Lab 2", code="LAB2", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], duration_periods=2, required_lab_type="CSE", room_type="THEORY", required_room_capacity=40),
    ]
    req.laboratories[0].required_subject_ids = ["LAB2"]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    for activity in result.activities:
        if activity.subject_id == "LAB2":
            assert activity.duration_periods == 2


def test_break_crossing_prevention(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.breaks.append(BreakTiming(name="Afternoon", start_time="12:40", end_time="13:30"))
    req.subjects = [
        Subject(id="LABX", name="Lab X", code="LABX", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], duration_periods=2, required_lab_type="CSE", room_type="THEORY", required_room_capacity=40),
    ]
    req.laboratories[0].required_subject_ids = ["LABX"]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    labs = [activity for activity in result.activities if activity.subject_id == "LABX"]
    assert len(labs) == 1
    assert labs[0].duration_periods == 2
    assert labs[0].period not in {2, 4}


def test_activity_overlapping_configured_break_is_rejected(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.breaks = [BreakTiming(name="Mid-period break", start_time="09:30", end_time="09:40")]
    req.faculty[0].available_days = ["Monday"]
    req.faculty[0].available_periods = {"Monday": [1]}
    req.classrooms = [
        Classroom(id="R1", name="Room 1", room_type="THEORY", capacity=60, available_days=["Monday"], available_periods={"Monday": [1]})
    ]
    req.subjects = [
        Subject(id="BREAK", name="Break overlap", code="BREAK", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status == "INFEASIBLE"


def test_exact_weekly_workload(basic_request):
    req = basic_request.model_copy(deep=True)
    req.subjects = [
        Subject(id="W1", name="W1", code="W1", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=3, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    assert sum(1 for a in result.activities if a.subject_id == "W1") == 3


def test_exact_lab_workload_and_fixed_duration(basic_request):
    req = basic_request.model_copy(deep=True)
    req.laboratories[0].required_subject_ids = ["EXACTLAB"]
    req.subjects = [
        Subject(id="EXACTLAB", name="Exact lab", code="EXACTLAB", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=4, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], duration_periods=5, required_lab_type="CSE", required_room_capacity=40),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    labs = [activity for activity in result.activities if activity.subject_id == "EXACTLAB"]
    assert len(labs) == 2
    assert all(activity.duration_periods == 2 for activity in labs)
    assert sum(activity.duration_periods for activity in labs) == 4


def test_no_fake_backfilling(basic_request):
    req = basic_request.model_copy(deep=True)
    req.subjects = [
        Subject(id="S", name="S", code="S", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    assert sum(1 for a in result.activities if a.subject_id == "S") == 1
    assert result.statistics.free_periods == 11


def test_fixed_slots_are_not_reported_as_free(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday"]
    req.existing_timetable = [
        ExistingActivity(id="FIXED-SLOT", day="Monday", period=1, division=req.division.name, batch_ids=["TB1", "TB2", "TB3"]),
    ]
    req.subjects = [
        Subject(id="ONE", name="One", code="ONE", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    assert result.activities[0].period != 1
    assert result.statistics.free_periods == 4


def test_faculty_workload_limit(basic_request):
    req = basic_request.model_copy(deep=True)
    req.faculty[0].max_workload = 1
    req.subjects = [
            Subject(id="WLOAD", name="Workload", code="WLOAD", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    total = sum(a.duration_periods for a in result.activities if a.faculty_id == "F1")
    assert total <= req.faculty[0].max_workload


def test_faculty_workload_exceeding_limit_is_infeasible(basic_request):
    req = basic_request.model_copy(deep=True)
    req.faculty[0].max_workload = 1
    req.subjects = [
        Subject(id="OVERLOAD", name="Overload", code="OVERLOAD", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    assert solve_basic(req).status == "INFEASIBLE"


def test_faculty_workload_counts_lab_duration(basic_request):
    req = basic_request.model_copy(deep=True)
    req.faculty[0].max_workload = 1
    req.laboratories[0].required_subject_ids = ["LONG-LAB"]
    req.subjects = [
        Subject(id="LONG-LAB", name="Long lab", code="LONG-LAB", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], required_lab_type="CSE", required_room_capacity=40),
    ]
    assert solve_basic(req).status == "INFEASIBLE"


def test_faculty_workload_includes_fixed_existing_activity(basic_request):
    req = basic_request.model_copy(deep=True)
    req.faculty[0].max_workload = 1
    req.existing_timetable = [
        ExistingActivity(id="FIXED-WORK", day="Monday", period=6, faculty_id="F1", fixed=True),
    ]
    req.subjects = [
        Subject(id="NEW-WORK", name="New work", code="NEW-WORK", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    assert solve_basic(req).status == "INFEASIBLE"


def test_faculty_replacement_uses_eligible_available_faculty(basic_request):
    req = basic_request.model_copy(deep=True)
    req.faculty[0].subject_ids = ["REPLACEMENT"]
    req.faculty[0].available_days = []
    req.faculty[1].subject_ids = ["REPLACEMENT"]
    req.subjects = [
        Subject(id="REPLACEMENT", name="Replacement", code="REPLACEMENT", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1", "F2"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    assert len(result.activities) == 1
    assert result.activities[0].faculty_id == "F2"


def test_ineligible_faculty_is_not_selected(basic_request):
    req = basic_request.model_copy(deep=True)
    req.faculty[0].subject_ids = ["OTHER"]
    req.faculty[1].subject_ids = ["ELIGIBLE"]
    req.subjects = [
        Subject(id="ELIGIBLE", name="Eligible", code="ELIGIBLE", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1", "F2"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    assert result.activities[0].faculty_id == "F2"


@pytest.mark.parametrize("target", ["faculty", "laboratory"])
@pytest.mark.parametrize(("periods", "expected_status"), [([3], "INFEASIBLE"), ([4], "INFEASIBLE"), ([3, 4], "FEASIBLE")])
def test_lab_requires_full_faculty_and_lab_interval(basic_request, target, periods, expected_status):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday"]
    req.faculty[0].available_days = ["Monday"]
    faculty_periods = periods if target == "faculty" else [3, 4]
    lab_periods = periods if target == "laboratory" else [3, 4]
    req.faculty[0].available_periods = {"Monday": faculty_periods}
    req.laboratories[0].available_days = ["Monday"]
    req.laboratories[0].available_periods = {"Monday": lab_periods}
    req.laboratories[0].required_subject_ids = ["INTERVAL"]
    req.subjects = [
        Subject(id="INTERVAL", name="Interval", code="INTERVAL", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], required_lab_type="CSE", required_room_capacity=40),
    ]
    result = solve_basic(req)
    if expected_status == "FEASIBLE":
        assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
        assert result.activities[0].period == 3
        assert result.activities[0].duration_periods == 2
    else:
        assert result.status == expected_status


def test_batch_conflict_checks_each_batch_of_parallel_assignment(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday"]
    for faculty in req.faculty:
        faculty.available_days = ["Monday"]
        faculty.available_periods = {"Monday": [1]}
    for room in req.classrooms:
        room.available_days = ["Monday"]
        room.available_periods = {"Monday": [1]}
    req.subjects = [
        Subject(id="PAR2", name="Parallel", code="PAR2", activity_type="THEORY", activity_mode="PARALLEL_BATCH", weekly_periods=1, faculty_ids=["F1", "F2"], applicable_batches=["TB1", "TB2"], room_type="THEORY", required_room_capacity=60),
        Subject(id="TB2ONLY", name="Batch 2", code="TB2ONLY", activity_type="THEORY", activity_mode="PARALLEL_BATCH", weekly_periods=1, faculty_ids=["F3"], applicable_batches=["TB2"], room_type="THEORY", required_room_capacity=60),
    ]
    assert solve_basic(req).status == "INFEASIBLE"


@pytest.mark.parametrize("conflict", ["faculty", "classroom", "laboratory", "division", "batch"])
def test_fixed_activity_partial_overlap_is_protected(basic_request, conflict):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday"]
    req.faculty[0].available_days = ["Monday"]
    req.faculty[0].available_periods = {"Monday": [3, 4]}
    if conflict == "classroom":
        req.classrooms = [Classroom(id="R1", name="Room 1", room_type="THEORY", capacity=60, available_days=["Monday"], available_periods={"Monday": [3]})]
        subject = Subject(id="FIXED", name="Fixed collision", code="FIXED", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60)
        existing = ExistingActivity(id="E1", day="Monday", period=2, duration_periods=2, classroom_id="R1")
    else:
        req.laboratories[0].available_days = ["Monday"]
        req.laboratories[0].available_periods = {"Monday": [3, 4]}
        req.laboratories[0].required_subject_ids = ["FIXED"]
        subject = Subject(id="FIXED", name="Fixed collision", code="FIXED", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], required_lab_type="CSE", required_room_capacity=40)
        existing = ExistingActivity(id="E1", day="Monday", period=2, duration_periods=2)
        if conflict == "faculty":
            existing.faculty_id = "F1"
        elif conflict == "laboratory":
            existing.laboratory_id = "L1"
        elif conflict == "division":
            existing.division = req.division.name
        else:
            existing.batch_ids = ["TB2"]
    req.subjects = [subject]
    req.existing_timetable = [existing]
    original_existing = [activity.model_dump() for activity in req.existing_timetable]
    result = solve_basic(req)
    assert result.status == "INFEASIBLE"
    assert [activity.model_dump() for activity in req.existing_timetable] == original_existing


@pytest.mark.parametrize("resource_key", ["faculty_id", "classroom_id", "laboratory_id"])
def test_interval_overlap_conflicts_for_each_resource(basic_request, resource_key):
    req = basic_request.model_copy(deep=True)
    left = {"candidate_id": "LEFT", "subject_id": "LEFT", "activity_type": "THEORY", "day": "Monday", "period": 3, "duration_periods": 2, "faculty_id": "F1", "classroom_id": "R1", "laboratory_id": None, "division": "TY CSE B", "batch_ids": ["TB1"], "activity_mode": "PARALLEL_BATCH", "activity_group_id": None}
    right = {"candidate_id": "RIGHT", "subject_id": "RIGHT", "activity_type": "THEORY", "day": "Monday", "period": 4, "duration_periods": 2, "faculty_id": "F2", "classroom_id": "R2", "laboratory_id": None, "division": "TY CSE B", "batch_ids": ["TB2"], "activity_mode": "PARALLEL_BATCH", "activity_group_id": None}
    shared_id = {"faculty_id": "F1", "classroom_id": "R1", "laboratory_id": "L1"}[resource_key]
    left[resource_key] = shared_id
    right[resource_key] = shared_id
    model = cp_model.CpModel()
    _, feasible = _add_constraints(req, model, [left, right], {"LEFT": [left], "RIGHT": [right]}, {})
    assert feasible
    assert cp_model.CpSolver().Solve(model) == cp_model.INFEASIBLE


@pytest.mark.parametrize("periods", [[3], [4], [3, 4]])
def test_resource_interval_availability_helper(basic_request, periods):
    room = Classroom(id="R1", name="Room 1", room_type="THEORY", capacity=60, available_days=["Monday"], available_periods={"Monday": periods})
    assert _resource_available(room, "Monday", 3, 2) is (periods == [3, 4])


def test_faculty_availability(basic_request):
    req = basic_request.model_copy(deep=True)
    req.faculty[0].available_days = ["Tuesday"]
    req.subjects = [
        Subject(id="A1", name="Avail", code="A1", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    assert all(a.faculty_id != "F1" or a.day == "Tuesday" for a in result.activities)


def test_classroom_capacity(basic_request):
    req = basic_request.model_copy(deep=True)
    req.classrooms[0].capacity = 20
    req.subjects = [
        Subject(id="CAP", name="Capacity", code="CAP", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    assert all(a.classroom_id is None or a.classroom_id != "R1" for a in result.activities)


def test_laboratory_capacity(basic_request):
    req = basic_request.model_copy(deep=True)
    req.laboratories = [
        Laboratory(id="L1", name="Small lab", lab_type="CSE", capacity=20, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4, 5, 6], "Tuesday": [1, 2, 3, 4, 5, 6]}, required_subject_ids=["LABC"], eligible_batches=["TB1", "TB2", "TB3"]),
        Laboratory(id="L2", name="Suitable lab", lab_type="CSE", capacity=40, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2, 3, 4, 5, 6], "Tuesday": [1, 2, 3, 4, 5, 6]}, required_subject_ids=["LABC"], eligible_batches=["TB1", "TB2", "TB3"]),
    ]
    req.subjects = [
            Subject(id="LABC", name="Lab Cap", code="LABC", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], duration_periods=2, required_lab_type="CSE", room_type="THEORY", required_room_capacity=40),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    assert any(activity.laboratory_id == "L2" for activity in result.activities)
    assert all(activity.laboratory_id != "L1" for activity in result.activities)


def test_infeasible_timetable(basic_request):
    req = basic_request.model_copy(deep=True)
    req.subjects = [
        Subject(id="INF1", name="INF1", code="INF1", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
        Subject(id="INF2", name="INF2", code="INF2", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    req.faculty[0].available_days = []
    result = solve_basic(req)
    assert result.status in {"INFEASIBLE", "TIME_LIMITED"}


def test_soft_constraint_optimization(basic_request):
    req = basic_request.model_copy(deep=True)
    req.subjects = [
        Subject(id="IMP", name="Important", code="IMP", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], important=True, applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"OPTIMAL", "FEASIBLE", "TIME_LIMITED"}
    assert any(activity.subject_id == "IMP" for activity in result.activities)


def test_time_limit_behavior(basic_request):
    req = basic_request.model_copy(deep=True)
    req.constraints.time_limit_seconds = 0.01
    req.subjects = [
        Subject(id="TL1", name="TL1", code="TL1", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=5, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
        Subject(id="TL2", name="TL2", code="TL2", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=5, faculty_ids=["F2"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status in {"INFEASIBLE", "TIME_LIMITED", "OPTIMAL", "FEASIBLE"}
    assert result.solve_time_seconds >= 0


def test_lab_can_run_before_first_break_when_necessary(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday"]
    req.faculty[0].available_days = ["Monday"]
    req.faculty[0].available_periods = {"Monday": [1, 2]}
    req.laboratories[0].available_days = ["Monday"]
    req.laboratories[0].available_periods = {"Monday": [1, 2]}
    req.laboratories[0].required_subject_ids = ["EARLY-LAB"]
    req.subjects = [
        Subject(id="EARLY-LAB", name="Early lab", code="EARLY-LAB", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], required_lab_type="CSE", required_room_capacity=40),
    ]
    result = solve_basic(req)
    assert result.status == "OPTIMAL"
    assert len(result.activities) == 1
    assert result.activities[0].period == 1


def test_lab_prefers_after_first_configured_break(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday"]
    req.settings.breaks = [BreakTiming(name="First break", start_time="12:40", end_time="13:30")]
    req.faculty[0].available_days = ["Monday"]
    req.faculty[0].available_periods = {"Monday": [1, 2, 3, 4, 5, 6]}
    req.laboratories[0].available_days = ["Monday"]
    req.laboratories[0].available_periods = {"Monday": [1, 2, 3, 4, 5, 6]}
    req.laboratories[0].required_subject_ids = ["LATE-LAB"]
    req.subjects = [
        Subject(id="LATE-LAB", name="Late lab", code="LATE-LAB", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], required_lab_type="CSE", required_room_capacity=40),
    ]
    result = solve_basic(req)
    assert result.status == "OPTIMAL"
    assert result.activities[0].period == 5


def test_important_subject_gets_preferred_slot(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday"]
    req.classrooms = [
        Classroom(id="R1", name="Room 1", room_type="THEORY", capacity=60, available_days=["Monday"], available_periods={"Monday": [1, 2]})
    ]
    for faculty in req.faculty[:2]:
        faculty.available_days = ["Monday"]
        faculty.available_periods = {"Monday": [1, 2]}
    req.subjects = [
        Subject(id="CORE", name="Core", code="CORE", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], important=True, applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
        Subject(id="OPTIONAL", name="Optional", code="OPTIONAL", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F2"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status == "OPTIMAL"
    placements = {activity.subject_id: activity.period for activity in result.activities}
    assert placements["CORE"] == 1
    assert placements["OPTIONAL"] == 2


def test_faculty_workload_objective_balances_assignments_including_fixed_work(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday"]
    req.existing_timetable = [
        ExistingActivity(id="FIXED-F1", day="Monday", period=5, duration_periods=2, faculty_id="F1"),
    ]
    for faculty in req.faculty[:2]:
        faculty.available_days = ["Monday"]
        faculty.available_periods = {"Monday": [1, 2, 3, 4]}
        faculty.max_workload = 8
    req.subjects = [
        Subject(id="BALANCE", name="Balance", code="BALANCE", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1", "F2"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status == "OPTIMAL"
    assert len(result.activities) == 1
    assert result.activities[0].faculty_id == "F2"


def test_daily_balance_spreads_one_faculty_across_days(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday", "Tuesday"]
    req.classrooms = [
        Classroom(id="R1", name="Room 1", room_type="THEORY", capacity=60, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1, 2], "Tuesday": [1, 2]})
    ]
    req.faculty[0].available_days = ["Monday", "Tuesday"]
    req.faculty[0].available_periods = {"Monday": [1, 2], "Tuesday": [1, 2]}
    req.subjects = [
        Subject(id="DAILY", name="Daily", code="DAILY", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status == "OPTIMAL"
    assert {activity.day for activity in result.activities} == {"Monday", "Tuesday"}


def test_daily_balance_spreads_batch_activities_across_days(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday", "Tuesday"]
    req.classrooms = [
        Classroom(id="R1", name="Room 1", room_type="THEORY", capacity=20, available_days=["Monday", "Tuesday"], available_periods={"Monday": [1], "Tuesday": [1]})
    ]
    for faculty in req.faculty[:2]:
        faculty.available_days = ["Monday", "Tuesday"]
        faculty.available_periods = {"Monday": [1], "Tuesday": [1]}
    req.subjects = [
        Subject(id="BATCH1", name="Batch 1", code="BATCH1", activity_type="THEORY", activity_mode="PARALLEL_BATCH", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1"], room_type="THEORY", required_room_capacity=20),
        Subject(id="BATCH2", name="Batch 2", code="BATCH2", activity_type="THEORY", activity_mode="PARALLEL_BATCH", weekly_periods=1, faculty_ids=["F2"], applicable_batches=["TB2"], room_type="THEORY", required_room_capacity=20),
    ]
    result = solve_basic(req)
    assert result.status == "OPTIMAL"
    assert len(result.activities) == 2
    assert {activity.day for activity in result.activities} == {"Monday", "Tuesday"}


def test_resource_objective_prefers_smallest_suitable_room(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday"]
    req.division.number_of_students = 15
    for batch in req.batches:
        batch.number_of_students = 5
    req.classrooms = [
        Classroom(id="SMALL", name="Small", room_type="THEORY", capacity=20, available_days=["Monday"], available_periods={"Monday": [1]}),
        Classroom(id="LARGE", name="Large", room_type="THEORY", capacity=60, available_days=["Monday"], available_periods={"Monday": [1]}),
    ]
    req.faculty[0].available_days = ["Monday"]
    req.faculty[0].available_periods = {"Monday": [1]}
    req.subjects = [
        Subject(id="ROOM", name="Room", code="ROOM", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=1, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=15),
    ]
    result = solve_basic(req)
    assert result.status == "OPTIMAL"
    assert result.activities[0].classroom_id == "SMALL"


def test_resource_objective_prefers_smallest_suitable_lab(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday"]
    req.division.number_of_students = 15
    for batch in req.batches:
        batch.number_of_students = 5
    req.faculty[0].available_days = ["Monday"]
    req.faculty[0].available_periods = {"Monday": [3, 4]}
    req.laboratories = [
        Laboratory(id="SMALL-LAB", name="Small lab", lab_type="CSE", capacity=20, available_days=["Monday"], available_periods={"Monday": [3, 4]}, required_subject_ids=["LAB-RESOURCE"], eligible_batches=["TB1", "TB2", "TB3"]),
        Laboratory(id="LARGE-LAB", name="Large lab", lab_type="CSE", capacity=60, available_days=["Monday"], available_periods={"Monday": [3, 4]}, required_subject_ids=["LAB-RESOURCE"], eligible_batches=["TB1", "TB2", "TB3"]),
    ]
    req.subjects = [
        Subject(id="LAB-RESOURCE", name="Lab resource", code="LAB-RESOURCE", activity_type="LAB", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], required_lab_type="CSE", required_room_capacity=15),
    ]
    result = solve_basic(req)
    assert result.status == "OPTIMAL"
    assert len(result.activities) == 1
    assert result.activities[0].laboratory_id == "SMALL-LAB"


def test_gap_objective_prefers_compact_schedule_without_backfilling(basic_request):
    req = basic_request.model_copy(deep=True)
    req.settings.working_days = ["Monday"]
    req.existing_timetable = [
        ExistingActivity(id="FIXED-FIRST", day="Monday", period=1, division=req.division.name, batch_ids=["TB1", "TB2", "TB3"]),
    ]
    req.classrooms = [
        Classroom(id="R1", name="Room 1", room_type="THEORY", capacity=60, available_days=["Monday"], available_periods={"Monday": [2, 3, 4]}),
    ]
    req.faculty[0].available_days = ["Monday"]
    req.faculty[0].available_periods = {"Monday": [2, 3, 4]}
    req.subjects = [
        Subject(id="COMPACT", name="Compact", code="COMPACT", activity_type="THEORY", activity_mode="WHOLE_DIVISION", weekly_periods=2, faculty_ids=["F1"], applicable_batches=["TB1", "TB2", "TB3"], room_type="THEORY", required_room_capacity=60),
    ]
    result = solve_basic(req)
    assert result.status == "OPTIMAL"
    assert sorted(activity.period for activity in result.activities) == [2, 3]
    assert len(result.activities) == 2
