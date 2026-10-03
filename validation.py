from __future__ import annotations

from datetime import datetime
from itertools import combinations
from typing import Iterable

from models import SolverRequest


WEEKDAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}


def _time_minutes(value: str) -> int:
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def _unique_ids(items: Iterable[object], label: str, errors: list[str]) -> set[str]:
    identifiers = [getattr(item, "id", "") for item in items]
    if any(not identifier for identifier in identifiers):
        errors.append(f"{label} IDs must be non-empty.")
    if len(identifiers) != len(set(identifiers)):
        errors.append(f"{label} IDs must be unique.")
    return set(identifiers)


def _validate_availability(entity, label: str, working_days: set[str], periods_per_day: int, errors: list[str]) -> None:
    if len(entity.available_days) != len(set(entity.available_days)):
        errors.append(f"{label} {entity.id} has duplicate available days.")
    unknown_days = set(entity.available_days) - working_days
    if unknown_days:
        errors.append(f"{label} {entity.id} references unknown working days: {sorted(unknown_days)}.")

    for day, periods in entity.available_periods.items():
        if day not in working_days:
            errors.append(f"{label} {entity.id} availability references unknown day {day}.")
        if len(periods) != len(set(periods)) or any(period < 1 or period > periods_per_day for period in periods):
            errors.append(f"{label} {entity.id} availability has invalid periods for {day}.")


def validate_solver_request(request: SolverRequest) -> list[str]:
    """Return request-data errors without changing the existing Pydantic contract."""
    errors: list[str] = []
    settings = request.settings
    working_days = set(settings.working_days)

    if not settings.working_days:
        errors.append("working_days must include at least one day.")
    if len(working_days) != len(settings.working_days):
        errors.append("working_days must not contain duplicates.")
    if working_days - WEEKDAYS:
        errors.append(f"working_days contains invalid days: {sorted(working_days - WEEKDAYS)}.")
    if settings.periods_per_day < 1:
        errors.append("periods_per_day must be at least 1.")

    periods_per_day = max(0, settings.periods_per_day)
    timing_periods = [timing.period for timing in settings.period_timings]
    expected_periods = set(range(1, periods_per_day + 1))
    if len(timing_periods) != len(set(timing_periods)):
        errors.append("period_timings must not contain duplicate period numbers.")
    if set(timing_periods) != expected_periods:
        errors.append("period_timings must define each period from 1 through periods_per_day exactly once.")

    timed_periods = []
    for timing in settings.period_timings:
        try:
            start = _time_minutes(timing.start_time)
            end = _time_minutes(timing.end_time)
        except ValueError:
            errors.append(f"Period {timing.period} has an invalid time; use HH:MM format.")
            continue
        if start >= end:
            errors.append(f"Period {timing.period} must end after it starts.")
        else:
            timed_periods.append((start, end, timing.period))
    timed_periods.sort()
    for previous, current in zip(timed_periods, timed_periods[1:]):
        if current[0] < previous[1]:
            errors.append(f"Periods {previous[2]} and {current[2]} overlap in time.")

    break_intervals = []
    for break_timing in settings.breaks:
        try:
            start = _time_minutes(break_timing.start_time)
            end = _time_minutes(break_timing.end_time)
        except ValueError:
            errors.append(f"Break {break_timing.name} has an invalid time; use HH:MM format.")
            continue
        if start >= end:
            errors.append(f"Break {break_timing.name} must end after it starts.")
        else:
            break_intervals.append((start, end, break_timing.name))
    break_intervals.sort()
    for previous, current in zip(break_intervals, break_intervals[1:]):
        if current[0] < previous[1]:
            errors.append(f"Breaks {previous[2]} and {current[2]} overlap.")

    if request.constraints.time_limit_seconds < 0:
        errors.append("time_limit_seconds must not be negative.")

    division = request.division
    if not division.id or not division.name or division.number_of_students <= 0:
        errors.append("division must have non-empty identifiers and a positive student count.")
    if len(division.batch_ids) != len(set(division.batch_ids)):
        errors.append("division.batch_ids must not contain duplicates.")

    batch_ids = _unique_ids(request.batches, "Batch", errors)
    if len(division.batch_ids) and batch_ids and not batch_ids.issubset(set(division.batch_ids)):
        errors.append("Every batch record must be listed in division.batch_ids.")
    for batch in request.batches:
        if batch.division not in {division.id, division.name}:
            errors.append(f"Batch {batch.id} references a different division.")
        if batch.number_of_students is not None and batch.number_of_students <= 0:
            errors.append(f"Batch {batch.id} must have a positive student count.")
    known_batch_ids = set(division.batch_ids) | batch_ids

    subject_ids = _unique_ids(request.subjects, "Subject", errors)
    faculty_ids = _unique_ids(request.faculty, "Faculty", errors)
    classroom_ids = _unique_ids(request.classrooms, "Classroom", errors)
    laboratory_ids = _unique_ids(request.laboratories, "Laboratory", errors)

    for subject in request.subjects:
        if subject.weekly_periods < 0:
            errors.append(f"Subject {subject.id} weekly_periods must not be negative.")
        if subject.activity_type == "LAB":
            if subject.weekly_periods % 2:
                errors.append(f"LAB subject {subject.id} weekly_periods must be a multiple of two periods.")
            if "duration_periods" in subject.model_fields_set and subject.duration_periods != 2:
                errors.append(f"LAB subject {subject.id} duration_periods must be exactly 2 when specified.")
        elif subject.duration_periods < 1:
            errors.append(f"Subject {subject.id} duration_periods must be positive.")
        if subject.required_room_capacity is not None and subject.required_room_capacity <= 0:
            errors.append(f"Subject {subject.id} required_room_capacity must be positive.")
        if subject.weekly_periods > 0 and not subject.faculty_ids:
            errors.append(f"Subject {subject.id} requires at least one faculty ID.")
        unknown_faculty = set(subject.faculty_ids) - faculty_ids
        if unknown_faculty:
            errors.append(f"Subject {subject.id} references unknown faculty: {sorted(unknown_faculty)}.")
        unknown_batches = set(subject.applicable_batches) - known_batch_ids
        if unknown_batches:
            errors.append(f"Subject {subject.id} references unknown batches: {sorted(unknown_batches)}.")
        if subject.activity_mode != "WHOLE_DIVISION" and subject.weekly_periods > 0 and not (subject.applicable_batches or division.batch_ids):
            errors.append(f"Subject {subject.id} requires batches for {subject.activity_mode} scheduling.")

    for faculty in request.faculty:
        if faculty.max_workload < 0:
            errors.append(f"Faculty {faculty.id} max_workload must not be negative.")
        _validate_availability(faculty, "Faculty", working_days, periods_per_day, errors)
        for slot in faculty.unavailable_slots:
            try:
                day, period_text = slot.rsplit(":", 1)
                period = int(period_text)
            except (ValueError, TypeError):
                errors.append(f"Faculty {faculty.id} has invalid unavailable slot {slot!r}.")
                continue
            if day not in working_days or period < 1 or period > periods_per_day:
                errors.append(f"Faculty {faculty.id} has unavailable slot outside the timetable: {slot!r}.")

    for classroom in request.classrooms:
        if classroom.capacity <= 0:
            errors.append(f"Classroom {classroom.id} capacity must be positive.")
        _validate_availability(classroom, "Classroom", working_days, periods_per_day, errors)

    for laboratory in request.laboratories:
        if laboratory.capacity <= 0:
            errors.append(f"Laboratory {laboratory.id} capacity must be positive.")
        _validate_availability(laboratory, "Laboratory", working_days, periods_per_day, errors)

    for existing in request.existing_timetable:
        if existing.day not in working_days:
            errors.append(f"Existing activity {existing.id} references unknown working day {existing.day}.")
        if existing.duration_periods < 1 or existing.period < 1 or existing.period + existing.duration_periods - 1 > periods_per_day:
            errors.append(f"Existing activity {existing.id} has an invalid period interval.")
        if existing.faculty_id and existing.faculty_id not in faculty_ids:
            errors.append(f"Existing activity {existing.id} references unknown faculty {existing.faculty_id}.")
        if existing.classroom_id and existing.classroom_id not in classroom_ids:
            errors.append(f"Existing activity {existing.id} references unknown classroom {existing.classroom_id}.")
        if existing.laboratory_id and existing.laboratory_id not in laboratory_ids:
            errors.append(f"Existing activity {existing.id} references unknown laboratory {existing.laboratory_id}.")
        if existing.division in {None, division.id, division.name}:
            unknown_batches = set(existing.batch_ids) - known_batch_ids
            if unknown_batches:
                errors.append(f"Existing activity {existing.id} references unknown batches: {sorted(unknown_batches)}.")

    return errors


def validate_solver_result(request: SolverRequest, result) -> list[str]:
    """Check the public schedule invariants before a successful result is returned."""
    errors: list[str] = []
    supported_statuses = {"OPTIMAL", "FEASIBLE", "INFEASIBLE", "TIME_LIMITED"}
    if result.status not in supported_statuses:
        return [f"Solver returned unsupported status {result.status!r}."]
    if result.status not in {"OPTIMAL", "FEASIBLE"}:
        if result.activities:
            errors.append(f"Solver status {result.status} must not include an unverified timetable.")
        return errors

    subjects = {subject.id: subject for subject in request.subjects}
    faculty_by_id = {faculty.id: faculty for faculty in request.faculty}
    classrooms = {room.id: room for room in request.classrooms}
    laboratories = {lab.id: lab for lab in request.laboratories}
    days = set(request.settings.working_days)
    occurrence_counts: dict[tuple[str, str], int] = {}
    faculty_loads = {faculty.id: 0 for faculty in request.faculty}
    occupied: dict[str, set[tuple[str, str, int]]] = {
        "faculty": set(),
        "classroom": set(),
        "laboratory": set(),
        "batch": set(),
    }
    division_slots: set[tuple[str, int]] = set()

    def activity_periods(activity) -> set[int]:
        return set(range(activity.period, activity.period + activity.duration_periods))

    def is_available(entity, day: str, periods: set[int]) -> bool:
        if day not in entity.available_days:
            return False
        if entity.available_periods:
            return day in entity.available_periods and periods.issubset(set(entity.available_periods[day]))
        return True

    def crosses_break(activity) -> bool:
        timings = {timing.period: timing for timing in request.settings.period_timings}
        first = timings.get(activity.period)
        last = timings.get(activity.period + activity.duration_periods - 1)
        if first is None or last is None:
            return True
        start = _time_minutes(first.start_time)
        end = _time_minutes(last.end_time)
        return any(
            start < _time_minutes(break_timing.end_time)
            and _time_minutes(break_timing.start_time) < end
            for break_timing in request.settings.breaks
        )

    for activity in result.activities:
        subject = subjects.get(activity.subject_id)
        if subject is None:
            errors.append(f"Activity references unknown subject {activity.subject_id}.")
            continue
        periods = activity_periods(activity)
        if activity.day not in days or activity.period < 1 or max(periods, default=0) > request.settings.periods_per_day:
            errors.append(f"Activity {activity.subject_id} has an invalid day or period interval.")
        if activity.duration_periods != (2 if subject.activity_type == "LAB" else 1):
            errors.append(f"Activity {activity.subject_id} has an invalid duration.")
        if activity.division != request.division.name or activity.activity_mode != subject.activity_mode or activity.activity_type != subject.activity_type:
            errors.append(f"Activity {activity.subject_id} has inconsistent division or subject metadata.")
        if crosses_break(activity):
            errors.append(f"Activity {activity.subject_id} overlaps a configured break.")

        candidate_batches = list(subject.applicable_batches or request.division.batch_ids)
        if subject.activity_mode == "WHOLE_DIVISION":
            unit = "division"
            if activity.batch_ids != candidate_batches:
                errors.append(f"Whole-division activity {activity.subject_id} has incorrect batch coverage.")
        else:
            if len(activity.batch_ids) != 1 or activity.batch_ids[0] not in candidate_batches:
                errors.append(f"Batch activity {activity.subject_id} has invalid batch assignment.")
                unit = activity.batch_ids[0] if activity.batch_ids else "<missing>"
            else:
                unit = activity.batch_ids[0]
        occurrence_key = (activity.subject_id, unit)
        occurrence_counts[occurrence_key] = occurrence_counts.get(occurrence_key, 0) + 1

        faculty = faculty_by_id.get(activity.faculty_id)
        if faculty is None:
            errors.append(f"Activity {activity.subject_id} references unknown faculty {activity.faculty_id}.")
        else:
            if activity.faculty_id not in subject.faculty_ids or (faculty.subject_ids and subject.id not in faculty.subject_ids):
                errors.append(f"Activity {activity.subject_id} uses an ineligible faculty member.")
            if not is_available(faculty, activity.day, periods) or any(f"{activity.day}:{period}" in faculty.unavailable_slots for period in periods):
                errors.append(f"Activity {activity.subject_id} uses unavailable faculty time.")
            faculty_loads[faculty.id] += activity.duration_periods
            for period in periods:
                slot = (faculty.id, activity.day, period)
                if slot in occupied["faculty"]:
                    errors.append(f"Faculty clash at {activity.day} period {period}.")
                occupied["faculty"].add(slot)

        if subject.activity_type == "LAB":
            lab = laboratories.get(activity.laboratory_id)
            if lab is None:
                errors.append(f"Activity {subject.id} references unknown laboratory {activity.laboratory_id}.")
            else:
                if subject.required_lab_type and lab.lab_type != subject.required_lab_type:
                    errors.append(f"Activity {subject.id} uses an incompatible laboratory type.")
                if subject.required_room_capacity is not None and lab.capacity < subject.required_room_capacity:
                    errors.append(f"Activity {subject.id} uses an undersized laboratory.")
                if lab.required_subject_ids and subject.id not in lab.required_subject_ids:
                    errors.append(f"Activity {subject.id} uses a laboratory that excludes the subject.")
                if lab.eligible_batches and not set(activity.batch_ids).issubset(set(lab.eligible_batches)):
                    errors.append(f"Activity {subject.id} uses a laboratory ineligible for its batches.")
                if not is_available(lab, activity.day, periods):
                    errors.append(f"Activity {subject.id} uses unavailable laboratory time.")
                for period in periods:
                    slot = (lab.id, activity.day, period)
                    if slot in occupied["laboratory"]:
                        errors.append(f"Laboratory clash at {activity.day} period {period}.")
                    occupied["laboratory"].add(slot)
            if activity.classroom_id is not None:
                errors.append(f"Lab activity {subject.id} unexpectedly has a classroom.")
        else:
            room = classrooms.get(activity.classroom_id)
            if room is None:
                errors.append(f"Activity {subject.id} references unknown classroom {activity.classroom_id}.")
            else:
                if subject.room_type and room.room_type != subject.room_type:
                    errors.append(f"Activity {subject.id} uses an incompatible classroom type.")
                if subject.required_room_capacity is not None and room.capacity < subject.required_room_capacity:
                    errors.append(f"Activity {subject.id} uses an undersized classroom.")
                if not is_available(room, activity.day, periods):
                    errors.append(f"Activity {subject.id} uses unavailable classroom time.")
                for period in periods:
                    slot = (room.id, activity.day, period)
                    if slot in occupied["classroom"]:
                        errors.append(f"Classroom clash at {activity.day} period {period}.")
                    occupied["classroom"].add(slot)
            if activity.laboratory_id is not None:
                errors.append(f"Non-lab activity {subject.id} unexpectedly has a laboratory.")

        for period in periods:
            division_slots.add((activity.day, period))
            for batch_id in activity.batch_ids:
                slot = (batch_id, activity.day, period)
                if slot in occupied["batch"]:
                    errors.append(f"Batch clash for {batch_id} at {activity.day} period {period}.")
                occupied["batch"].add(slot)

    for subject in request.subjects:
        duration = 2 if subject.activity_type == "LAB" else 1
        expected_count = subject.weekly_periods // duration
        units = ["division"] if subject.activity_mode == "WHOLE_DIVISION" else list(subject.applicable_batches or request.division.batch_ids)
        for unit in units:
            if occurrence_counts.get((subject.id, unit), 0) != expected_count:
                errors.append(f"Subject {subject.id} has an incomplete or extra weekly workload for {unit}.")

    for faculty in request.faculty:
        fixed_load = sum(
            activity.duration_periods
            for activity in request.existing_timetable
            if activity.fixed and activity.faculty_id == faculty.id
        )
        if fixed_load + faculty_loads[faculty.id] > faculty.max_workload:
            errors.append(f"Faculty {faculty.id} exceeds max_workload.")

    activities = result.activities
    for left_index, left in enumerate(activities):
        left_periods = activity_periods(left)
        for right in activities[left_index + 1:]:
            if left.day != right.day or not left_periods.intersection(activity_periods(right)):
                continue
            if left.activity_mode == "WHOLE_DIVISION" or right.activity_mode == "WHOLE_DIVISION":
                errors.append(f"Whole-division slot clash at {left.day}.")
            elif left.activity_mode == "ROTATIONAL_BATCH" or right.activity_mode == "ROTATIONAL_BATCH":
                left_subject = subjects.get(left.subject_id)
                right_subject = subjects.get(right.subject_id)
                same_rotation = (
                    left.activity_mode == right.activity_mode == "ROTATIONAL_BATCH"
                    and left_subject is not None
                    and right_subject is not None
                    and left_subject.activity_group_id == right_subject.activity_group_id
                )
                if not same_rotation:
                    errors.append(f"Division rotation clash at {left.day}.")

    for activity in activities:
        periods = activity_periods(activity)
        for fixed in request.existing_timetable:
            if not fixed.fixed or activity.day != fixed.day or not periods.intersection(activity_periods(fixed)):
                continue
            if fixed.faculty_id and activity.faculty_id == fixed.faculty_id:
                errors.append(f"Activity {activity.subject_id} conflicts with fixed faculty {fixed.faculty_id}.")
            if fixed.classroom_id and activity.classroom_id == fixed.classroom_id:
                errors.append(f"Activity {activity.subject_id} conflicts with fixed classroom {fixed.classroom_id}.")
            if fixed.laboratory_id and activity.laboratory_id == fixed.laboratory_id:
                errors.append(f"Activity {activity.subject_id} conflicts with fixed laboratory {fixed.laboratory_id}.")
            if fixed.division in {request.division.id, request.division.name}:
                errors.append(f"Activity {activity.subject_id} conflicts with the fixed division timetable.")
            if set(fixed.batch_ids).intersection(activity.batch_ids):
                errors.append(f"Activity {activity.subject_id} conflicts with a fixed batch activity.")

    expected_periods = sum(
        subject.weekly_periods * (1 if subject.activity_mode == "WHOLE_DIVISION" else len(subject.applicable_batches or request.division.batch_ids))
        for subject in request.subjects
    )
    scheduled_periods = sum(activity.duration_periods for activity in activities)
    occupied_slots = set(division_slots)
    occupied_slots.update(
        (fixed.day, period)
        for fixed in request.existing_timetable
        if fixed.fixed
        for period in range(fixed.period, fixed.period + fixed.duration_periods)
    )
    timetable_capacity = len(request.settings.working_days) * request.settings.periods_per_day
    expected_free_periods = max(0, timetable_capacity - len(occupied_slots))
    if result.statistics.requested_periods != expected_periods:
        errors.append("Solver statistics requested_periods does not match the request.")
    if result.statistics.scheduled_periods != scheduled_periods or scheduled_periods != expected_periods:
        errors.append("Solver statistics scheduled_periods does not match the required workload.")
    if result.statistics.free_periods != expected_free_periods:
        errors.append("Solver statistics free_periods does not match timetable occupancy.")
    return errors
