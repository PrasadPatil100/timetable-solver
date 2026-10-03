from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ortools.sat.python import cp_model

from constraints import (
    has_break_crossing,
    is_day_available,
    is_period_available,
    period_range_for_duration,
    starts_after_first_break,
)
from converter import convert_to_activities
from models import GeneratedActivity, SolverRequest, SolverResult


SOFT_WEIGHTS = {
    "S1": 3,
    "S2": 4,
    "S3": 2,
    "S4": 2,
    "S5": 1,
    "S6": 3,
}


def _lookup(items: Iterable[Any], item_id: str) -> Optional[Any]:
    for item in items:
        if getattr(item, "id", None) == item_id:
            return item
    return None


def _candidate_batches(subject, division, fallback_batches: Optional[List[str]] = None) -> List[str]:
    if subject.applicable_batches:
        return list(subject.applicable_batches)
    if fallback_batches:
        return list(fallback_batches)
    if getattr(divide := division, "batch_ids", None):
        return list(division.batch_ids)
    return []


def _room_matches(room, subject):
    if subject.room_type and room.room_type != subject.room_type:
        return False
    if subject.required_room_capacity is not None and room.capacity < subject.required_room_capacity:
        return False
    return True


def _lab_matches(lab, subject, batch_ids):
    if subject.required_lab_type and lab.lab_type != subject.required_lab_type:
        return False
    if subject.required_room_capacity is not None and lab.capacity < subject.required_room_capacity:
        return False
    if lab.required_subject_ids and subject.id not in lab.required_subject_ids:
        return False
    if batch_ids and lab.eligible_batches and not set(batch_ids).issubset(set(lab.eligible_batches)):
        return False
    return True


def _faculty_is_eligible(request, subject, day, start_period, duration, faculty_id):
    faculty = _lookup(request.faculty, faculty_id)
    if faculty is None:
        return False
    if faculty.subject_ids and subject.id not in faculty.subject_ids:
        return False
    if not is_day_available(faculty.available_days, day):
        return False
    for period in range(start_period, start_period + duration):
        if not is_period_available(faculty.available_periods, day, period):
            return False
        if f"{day}:{period}" in faculty.unavailable_slots:
            return False
    return True


def _resource_available(entity, day, start_period, duration):
    if not is_day_available(entity.available_days, day):
        return False
    return all(
        is_period_available(entity.available_periods, day, period)
        for period in range(start_period, start_period + duration)
    )


def _occupied_periods(start_period: int, duration_periods: int) -> set[int]:
    return set(range(start_period, start_period + duration_periods))


def _existing_conflicts(candidate: dict, existing_activity) -> bool:
    if not existing_activity.fixed:
        return False
    if candidate["day"] != existing_activity.day:
        return False
    candidate_periods = _occupied_periods(candidate["period"], candidate["duration_periods"])
    existing_periods = _occupied_periods(existing_activity.period, existing_activity.duration_periods)
    if not candidate_periods.intersection(existing_periods):
        return False

    # Each identity is checked independently so sparse fixed entries still block
    # any conflict they can establish from their populated fields.
    if candidate.get("faculty_id") and existing_activity.faculty_id and candidate["faculty_id"] == existing_activity.faculty_id:
        return True
    if candidate.get("classroom_id") and existing_activity.classroom_id and candidate["classroom_id"] == existing_activity.classroom_id:
        return True
    if candidate.get("laboratory_id") and existing_activity.laboratory_id and candidate["laboratory_id"] == existing_activity.laboratory_id:
        return True
    candidate_divisions = {candidate["division"], candidate.get("division_id")}
    if existing_activity.division and existing_activity.division in candidate_divisions:
        return True
    if existing_activity.batch_ids and set(candidate.get("batch_ids", [])) & set(existing_activity.batch_ids):
        return True
    return False


def _build_candidates(request: SolverRequest):
    days = request.settings.working_days
    periods_per_day = request.settings.periods_per_day
    period_timings = [p.model_dump() for p in request.settings.period_timings]
    breaks = [b.model_dump() for b in request.settings.breaks]

    candidates: List[dict] = []
    occurrence_to_vars: Dict[str, List[Any]] = {}
    sync_groups: Dict[str, List[str]] = {}
    rotation_counts: Dict[str, set[int]] = {}

    for subject in request.subjects:
        duration = 2 if subject.activity_type == "LAB" else 1
        if subject.weekly_periods % duration:
            occurrence_to_vars[f"invalid_workload_{subject.id}"] = []
            continue
        occurrence_count = subject.weekly_periods // duration
        subject_batches = _candidate_batches(subject, request.division, request.division.batch_ids)

        if subject.activity_mode == "WHOLE_DIVISION":
            assignment_units = [("division", subject_batches)]
        else:
            assignment_units = [(batch_id, [batch_id]) for batch_id in subject_batches]

        if subject.activity_mode == "ROTATIONAL_BATCH" and not subject.activity_group_id:
            occurrence_to_vars[f"missing_rotation_group_{subject.id}"] = []
            continue
        if subject.activity_mode == "ROTATIONAL_BATCH":
            rotation_counts.setdefault(subject.activity_group_id, set()).add(occurrence_count)

        for occurrence_index in range(occurrence_count):
            unit_occurrences = []
            for unit_id, batch_ids in assignment_units:
                occurrence_id = f"{subject.id}_{occurrence_index}_{unit_id}"
                occurrence_to_vars[occurrence_id] = []
                unit_occurrences.append(occurrence_id)

                if subject.activity_mode == "PARALLEL_BATCH":
                    sync_key = f"parallel:{subject.id}:{occurrence_index}"
                    sync_groups.setdefault(sync_key, []).append(occurrence_id)
                elif subject.activity_mode == "ROTATIONAL_BATCH":
                    sync_key = f"rotation:{subject.activity_group_id}:{occurrence_index}"
                    sync_groups.setdefault(sync_key, []).append(occurrence_id)

                for day in days:
                    for start_period in range(1, periods_per_day + 1):
                        if start_period + duration - 1 > periods_per_day:
                            continue
                        if has_break_crossing(start_period, duration, period_timings, breaks):
                            continue

                        for faculty_id in subject.faculty_ids:
                            if not _faculty_is_eligible(request, subject, day, start_period, duration, faculty_id):
                                continue

                            resources = request.laboratories if subject.activity_type == "LAB" else request.classrooms
                            for resource in resources:
                                if subject.activity_type == "LAB":
                                    if not _lab_matches(resource, subject, batch_ids):
                                        continue
                                elif not _room_matches(resource, subject):
                                    continue
                                if not _resource_available(resource, day, start_period, duration):
                                    continue

                                candidate = {
                                    "candidate_id": f"{occurrence_id}_{day}_{start_period}_{faculty_id}_{resource.id}",
                                    "occurrence_id": occurrence_id,
                                    "subject_id": subject.id,
                                    "subject_name": subject.name,
                                    "day": day,
                                    "period": start_period,
                                    "duration_periods": duration,
                                    "faculty_id": faculty_id,
                                    "division": request.division.name,
                                    "division_id": request.division.id,
                                    "batch_ids": list(batch_ids),
                                    "classroom_id": resource.id if subject.activity_type != "LAB" else None,
                                    "laboratory_id": resource.id if subject.activity_type == "LAB" else None,
                                    "activity_type": subject.activity_type,
                                    "activity_mode": subject.activity_mode,
                                    "activity_group_id": subject.activity_group_id,
                                }
                                if any(_existing_conflicts(candidate, existing) for existing in request.existing_timetable):
                                    continue
                                occurrence_to_vars[occurrence_id].append(candidate)
                                candidates.append(candidate)

    for group_id, counts in rotation_counts.items():
        if len(counts) > 1:
            occurrence_to_vars[f"inconsistent_rotation_{group_id}"] = []

    return candidates, occurrence_to_vars, sync_groups


def _add_s1_terms(request: SolverRequest, candidates: List[dict]) -> List[Any]:
    if not request.constraints.prefer_labs_after_first_break or not request.settings.breaks:
        return []
    period_timings = [timing.model_dump() for timing in request.settings.period_timings]
    breaks = [break_timing.model_dump() for break_timing in request.settings.breaks]
    return [
        SOFT_WEIGHTS["S1"] * candidate["var"]
        for candidate in candidates
        if candidate["activity_type"] == "LAB"
        and starts_after_first_break(candidate["period"], period_timings, breaks)
    ]


def _add_s2_terms(request: SolverRequest, candidates: List[dict]) -> List[Any]:
    if not request.constraints.prioritize_important_subjects:
        return []
    important_subject_ids = {subject.id for subject in request.subjects if subject.important}
    if not important_subject_ids:
        return []
    ordered_periods = sorted(
        request.settings.period_timings,
        key=lambda timing: timing.start_time,
    )
    period_score = {
        timing.period: len(ordered_periods) - index - 1
        for index, timing in enumerate(ordered_periods)
    }
    return [
        SOFT_WEIGHTS["S2"] * period_score.get(candidate["period"], 0) * candidate["var"]
        for candidate in candidates
        if candidate["subject_id"] in important_subject_ids
    ]


def _faculty_workload_expression(request: SolverRequest, faculty, candidates: List[dict]):
    fixed_load = sum(
        activity.duration_periods
        for activity in request.existing_timetable
        if activity.fixed and activity.faculty_id == faculty.id
    )
    generated_load = sum(
        candidate["duration_periods"] * candidate["var"]
        for candidate in candidates
        if candidate.get("faculty_id") == faculty.id
    )
    return fixed_load + generated_load, fixed_load


def _add_absolute_difference(model: cp_model.CpModel, left, right, upper_bound: int, name: str):
    difference = model.NewIntVar(0, max(0, upper_bound), name)
    model.AddAbsEquality(difference, left - right)
    return difference


def _slot_occupancies(request: SolverRequest, model: cp_model.CpModel, candidates: List[dict]):
    candidate_slots: Dict[Tuple[str, str, str, int], List[Any]] = {}
    fixed_slots = set()

    for candidate in candidates:
        periods = period_range_for_duration(
            candidate["period"], candidate["duration_periods"], request.settings.periods_per_day
        )
        candidate_slots.setdefault(("division", request.division.id, candidate["day"], periods[0]), [])
        for period in periods:
            candidate_slots.setdefault(("division", request.division.id, candidate["day"], period), []).append(candidate["var"])
            for batch_id in candidate.get("batch_ids", []):
                candidate_slots.setdefault(("batch", batch_id, candidate["day"], period), []).append(candidate["var"])
            if candidate.get("faculty_id"):
                candidate_slots.setdefault(("faculty", candidate["faculty_id"], candidate["day"], period), []).append(candidate["var"])

    division_batch_ids = set(request.division.batch_ids) | {batch.id for batch in request.batches}
    for activity in request.existing_timetable:
        if not activity.fixed:
            continue
        periods = period_range_for_duration(
            activity.period, activity.duration_periods, request.settings.periods_per_day
        )
        if activity.division in {request.division.id, request.division.name} or set(activity.batch_ids) & division_batch_ids:
            fixed_slots.update(("division", request.division.id, activity.day, period) for period in periods)
        for batch_id in set(activity.batch_ids) & division_batch_ids:
            fixed_slots.update(("batch", batch_id, activity.day, period) for period in periods)
        if activity.faculty_id:
            fixed_slots.update(("faculty", activity.faculty_id, activity.day, period) for period in periods)

    occupancies = {}
    entity_ids = {
        "division": [request.division.id],
        "batch": sorted(division_batch_ids),
        "faculty": [faculty.id for faculty in request.faculty],
    }
    for kind, identifiers in entity_ids.items():
        for identifier in identifiers:
            for day in request.settings.working_days:
                for period in range(1, request.settings.periods_per_day + 1):
                    key = (kind, identifier, day, period)
                    variable = model.NewBoolVar(f"soft_occupied_{kind}_{identifier}_{day}_{period}")
                    if key in fixed_slots:
                        model.Add(variable == 1)
                    elif candidate_slots.get(key):
                        model.AddMaxEquality(variable, candidate_slots[key])
                    else:
                        model.Add(variable == 0)
                    occupancies[key] = variable
    return occupancies


def _daily_load_balance_terms(request: SolverRequest, model: cp_model.CpModel, candidates: List[dict], occupancies) -> List[Any]:
    if not request.constraints.balance_daily_schedule or len(request.settings.working_days) < 2:
        return []
    terms: List[Any] = []
    days = request.settings.working_days
    max_workload = max((faculty.max_workload for faculty in request.faculty), default=0)

    for faculty in request.faculty:
        daily_loads = []
        for day in days:
            fixed_load = sum(
                activity.duration_periods
                for activity in request.existing_timetable
                if activity.fixed and activity.faculty_id == faculty.id and activity.day == day
            )
            generated_load = sum(
                candidate["duration_periods"] * candidate["var"]
                for candidate in candidates
                if candidate.get("faculty_id") == faculty.id and candidate["day"] == day
            )
            daily_loads.append(fixed_load + generated_load)
        for left_index, left in enumerate(daily_loads):
            for right_index, right in enumerate(daily_loads[left_index + 1:], left_index + 1):
                difference = _add_absolute_difference(
                    model, left, right, max_workload, f"soft_faculty_day_diff_{faculty.id}_{left_index}_{right_index}"
                )
                terms.append(-SOFT_WEIGHTS["S4"] * difference)

    entities = [("division", request.division.id)]
    entities.extend(("batch", batch_id) for batch_id in sorted({batch.id for batch in request.batches} | set(request.division.batch_ids)))
    for kind, identifier in entities:
        daily_loads = [
            sum(
                occupancies[(kind, identifier, day, period)]
                for period in range(1, request.settings.periods_per_day + 1)
            )
            for day in days
        ]
        for left_index, left in enumerate(daily_loads):
            for right_index, right in enumerate(daily_loads[left_index + 1:], left_index + 1):
                difference = _add_absolute_difference(
                    model,
                    left,
                    right,
                    request.settings.periods_per_day,
                    f"soft_{kind}_day_diff_{identifier}_{left_index}_{right_index}",
                )
                terms.append(-SOFT_WEIGHTS["S4"] * difference)
    return terms


def _add_s3_terms(request: SolverRequest, model: cp_model.CpModel, candidates: List[dict]) -> List[Any]:
    if not request.constraints.balance_faculty_workload or len(request.faculty) < 2:
        return []
    loads = []
    bounds = []
    for faculty in request.faculty:
        load, fixed_load = _faculty_workload_expression(request, faculty, candidates)
        loads.append((faculty, load))
        bounds.append(max(faculty.max_workload, fixed_load))
    upper_bound = max(bounds, default=0)
    terms = []
    for left_index, (left_faculty, left_load) in enumerate(loads):
        for right_index, (right_faculty, right_load) in enumerate(loads[left_index + 1:], left_index + 1):
            difference = _add_absolute_difference(
                model,
                left_load,
                right_load,
                upper_bound,
                f"soft_faculty_total_diff_{left_faculty.id}_{right_faculty.id}",
            )
            terms.append(-SOFT_WEIGHTS["S3"] * difference)
    return terms


def _add_s4_terms(request: SolverRequest, model: cp_model.CpModel, candidates: List[dict]) -> List[Any]:
    if not request.constraints.balance_daily_schedule or len(request.settings.working_days) < 2:
        return []
    occupancies = _slot_occupancies(request, model, candidates)
    return _daily_load_balance_terms(request, model, candidates, occupancies)


def _add_s5_terms(request: SolverRequest, candidates: List[dict]) -> List[Any]:
    if not request.constraints.efficient_resource_utilization:
        return []
    resources = {resource.id: resource for resource in request.classrooms + request.laboratories}
    subjects = {subject.id: subject for subject in request.subjects}
    batch_sizes = {batch.id: batch.number_of_students or 0 for batch in request.batches}
    terms = []
    for candidate in candidates:
        resource_id = candidate.get("classroom_id") or candidate.get("laboratory_id")
        resource = resources.get(resource_id)
        subject = subjects.get(candidate["subject_id"])
        if resource is None or subject is None:
            continue
        assigned_students = sum(batch_sizes.get(batch_id, 0) for batch_id in candidate.get("batch_ids", []))
        if candidate["activity_mode"] == "WHOLE_DIVISION":
            assigned_students = max(assigned_students, request.division.number_of_students)
        required_capacity = max(subject.required_room_capacity or 0, assigned_students)
        excess_capacity = max(0, resource.capacity - required_capacity)
        excess_units = min(20, excess_capacity)
        terms.append(-SOFT_WEIGHTS["S5"] * excess_units * candidate["var"])
    return terms


def _add_s6_terms(request: SolverRequest, model: cp_model.CpModel, candidates: List[dict]) -> List[Any]:
    if not request.constraints.minimize_unnecessary_gaps:
        return []
    occupancies = _slot_occupancies(request, model, candidates)
    entities = [("division", request.division.id)]
    entities.extend(("batch", batch_id) for batch_id in sorted({batch.id for batch in request.batches} | set(request.division.batch_ids)))
    entities.extend(("faculty", faculty.id) for faculty in request.faculty)
    terms = []
    period_count = request.settings.periods_per_day
    for kind, identifier in entities:
        for day in request.settings.working_days:
            day_slots = [
                occupancies[(kind, identifier, day, period)]
                for period in range(1, period_count + 1)
            ]
            for period in range(1, period_count - 1):
                before = model.NewBoolVar(f"soft_before_{kind}_{identifier}_{day}_{period}")
                after = model.NewBoolVar(f"soft_after_{kind}_{identifier}_{day}_{period}")
                model.AddMaxEquality(before, day_slots[:period])
                model.AddMaxEquality(after, day_slots[period + 1:])
                gap = model.NewBoolVar(f"soft_gap_{kind}_{identifier}_{day}_{period + 1}")
                model.AddBoolAnd([before, after, day_slots[period].Not()]).OnlyEnforceIf(gap)
                model.AddBoolOr([before.Not(), after.Not(), day_slots[period]]).OnlyEnforceIf(gap.Not())
                terms.append(-SOFT_WEIGHTS["S6"] * gap)
    return terms


def _build_soft_objective(request: SolverRequest, model: cp_model.CpModel, candidates: List[dict]) -> List[Any]:
    terms = []
    terms.extend(_add_s1_terms(request, candidates))
    terms.extend(_add_s2_terms(request, candidates))
    terms.extend(_add_s3_terms(request, model, candidates))
    terms.extend(_add_s4_terms(request, model, candidates))
    terms.extend(_add_s5_terms(request, candidates))
    terms.extend(_add_s6_terms(request, model, candidates))
    return terms


def _add_constraints(request: SolverRequest, model: cp_model.CpModel, candidates: List[dict], occurrence_to_vars: Dict[str, List[Any]], sync_groups: Dict[str, List[str]]) -> tuple[dict, bool]:
    bool_vars: Dict[str, Any] = {}
    for candidate in candidates:
        variable = model.NewBoolVar(candidate["candidate_id"])
        bool_vars[candidate["candidate_id"]] = variable
        candidate["var"] = variable

    for occurrence_id, selected in occurrence_to_vars.items():
        if not selected:
            return bool_vars, False
        model.AddExactlyOne([candidate["var"] for candidate in selected])

    def add_interval_clashes(resource_key: str) -> None:
        grouped: Dict[Tuple[str, str, int], List[Any]] = {}
        for candidate in candidates:
            resource_id = candidate.get(resource_key)
            if not resource_id:
                continue
            for period in period_range_for_duration(candidate["period"], candidate["duration_periods"], request.settings.periods_per_day):
                key = (resource_id, candidate["day"], period)
                grouped.setdefault(key, []).append(candidate["var"])
        for variables in grouped.values():
            if len(variables) > 1:
                model.AddAtMostOne(variables)

    add_interval_clashes("faculty_id")
    add_interval_clashes("classroom_id")
    add_interval_clashes("laboratory_id")

    batch_grouped: Dict[Tuple[str, str, int], List[Any]] = {}
    for candidate in candidates:
        for batch_id in set(candidate.get("batch_ids", [])):
            for period in period_range_for_duration(candidate["period"], candidate["duration_periods"], request.settings.periods_per_day):
                batch_grouped.setdefault((batch_id, candidate["day"], period), []).append(candidate["var"])
    for variables in batch_grouped.values():
        if len(variables) > 1:
            model.AddAtMostOne(variables)

    for candidate_ids in sync_groups.values():
        occurrence_candidates = [occurrence_to_vars[occurrence_id] for occurrence_id in candidate_ids]
        if len(occurrence_candidates) < 2:
            continue
        slots = {
            (candidate["day"], candidate["period"])
            for group in occurrence_candidates
            for candidate in group
        }
        reference = occurrence_candidates[0]
        for other in occurrence_candidates[1:]:
            for day, period in slots:
                reference_vars = [candidate["var"] for candidate in reference if candidate["day"] == day and candidate["period"] == period]
                other_vars = [candidate["var"] for candidate in other if candidate["day"] == day and candidate["period"] == period]
                model.Add(sum(reference_vars) == sum(other_vars))

    division_grouped: Dict[Tuple[str, int], List[dict]] = {}
    for candidate in candidates:
        for period in period_range_for_duration(candidate["period"], candidate["duration_periods"], request.settings.periods_per_day):
            division_grouped.setdefault((candidate["day"], period), []).append(candidate)

    constrained_pairs = set()
    for slot_candidates in division_grouped.values():
        for left_index, left in enumerate(slot_candidates):
            for right in slot_candidates[left_index + 1:]:
                left_mode = left["activity_mode"]
                right_mode = right["activity_mode"]
                if left_mode != "WHOLE_DIVISION" and right_mode != "WHOLE_DIVISION":
                    same_rotation = (
                        left_mode == right_mode == "ROTATIONAL_BATCH"
                        and left.get("activity_group_id") == right.get("activity_group_id")
                    )
                    if not (left_mode == "ROTATIONAL_BATCH" or right_mode == "ROTATIONAL_BATCH") or same_rotation:
                        continue
                pair = tuple(sorted((left["candidate_id"], right["candidate_id"])))
                if pair not in constrained_pairs:
                    model.AddAtMostOne([left["var"], right["var"]])
                    constrained_pairs.add(pair)

    # Faculty workload limits.
    for faculty in request.faculty:
        workload_vars: List[Any] = []
        workload_weights: List[int] = []
        fixed_workload = sum(
            activity.duration_periods
            for activity in request.existing_timetable
            if activity.fixed and activity.faculty_id == faculty.id
        )
        for candidate in candidates:
            if candidate.get("faculty_id") != faculty.id:
                continue
            workload_vars.append(candidate["var"])
            workload_weights.append(candidate["duration_periods"])
        model.Add(
            fixed_workload + sum(weight * var for weight, var in zip(workload_weights, workload_vars))
            <= faculty.max_workload
        )

    # Required occurrences remain mandatory; these terms only choose among hard-feasible candidates.
    objective_terms = _build_soft_objective(request, model, candidates)
    if objective_terms:
        model.Maximize(sum(objective_terms))

    return bool_vars, True


def solve_basic(request: SolverRequest) -> SolverResult:
    model = cp_model.CpModel()
    candidates, occurrence_to_vars, sync_groups = _build_candidates(request)
    bool_vars, feasible_model = _add_constraints(request, model, candidates, occurrence_to_vars, sync_groups)
    if not feasible_model:
        return SolverResult(
            status="INFEASIBLE",
            warnings=["At least one required subject occurrence has no valid timetable slot or resource combination."],
            violations=["No feasible slot/resource combinations available for at least one subject occurrence."],
            statistics={
                "requested_periods": sum(subject.weekly_periods for subject in request.subjects),
                "scheduled_periods": 0,
                "free_periods": len(request.settings.working_days) * request.settings.periods_per_day,
                "solver_time_seconds": 0.0,
            },
        )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(request.constraints.time_limit_seconds)
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)

    if status == cp_model.UNKNOWN:
        result_status = "TIME_LIMITED"
    elif status == cp_model.INFEASIBLE:
        result_status = "INFEASIBLE"
    elif status == cp_model.OPTIMAL:
        result_status = "OPTIMAL"
    else:
        result_status = "FEASIBLE"

    selected = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        selected = [candidate for candidate in candidates if solver.Value(bool_vars[candidate["candidate_id"]]) == 1]

    activities = convert_to_activities(selected, request.settings.working_days)

    warnings = []
    if result_status == "TIME_LIMITED":
        warnings.append("Search was time-limited before proving optimality; the best available schedule is returned.")
    if result_status == "INFEASIBLE":
        warnings.append("No feasible timetable could be constructed under the hard constraints.")

    requested_periods = sum(
        subject.weekly_periods * (1 if subject.activity_mode == "WHOLE_DIVISION" else len(_candidate_batches(subject, request.division, request.division.batch_ids)))
        for subject in request.subjects
    )
    scheduled_periods = sum(activity.duration_periods for activity in activities)
    occupied_division_slots = {
        (activity.day, period)
        for activity in activities
        for period in period_range_for_duration(activity.period, activity.duration_periods, request.settings.periods_per_day)
    }
    occupied_division_slots.update(
        (activity.day, period)
        for activity in request.existing_timetable
        if activity.fixed
        for period in period_range_for_duration(activity.period, activity.duration_periods, request.settings.periods_per_day)
    )
    free_periods = len(request.settings.working_days) * request.settings.periods_per_day - len(occupied_division_slots)

    return SolverResult(
        status=result_status,
        solve_time_seconds=solver.WallTime(),
        activities=activities,
        warnings=warnings,
        violations=[] if result_status != "INFEASIBLE" else ["No feasible timetable under the provided constraints."],
        statistics={
            "requested_periods": requested_periods,
            "scheduled_periods": scheduled_periods,
            "free_periods": max(0, free_periods),
            "solver_time_seconds": solver.WallTime(),
        },
    )