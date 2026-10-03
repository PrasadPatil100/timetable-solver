from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple


def period_range_for_duration(start_period: int, duration_periods: int, periods_per_day: int) -> List[int]:
    periods = []
    for offset in range(duration_periods):
        period = start_period + offset
        if 1 <= period <= periods_per_day:
            periods.append(period)
    return periods


def is_period_available(available_periods: Optional[dict[str, list[int]]], day: str, period: int) -> bool:
    if not available_periods:
        return True
    return day in available_periods and period in available_periods[day]


def is_day_available(available_days: Sequence[str], day: str) -> bool:
    if not available_days:
        return False
    return day in available_days


def _time_minutes(value: str) -> float:
    hour, minute, *seconds = map(int, value.split(":"))
    return hour * 60 + minute + (seconds[0] / 60 if seconds else 0)


def starts_after_first_break(start_period: int, period_timings: Sequence[dict], breaks: Sequence[dict]) -> bool:
    if not breaks:
        return False
    first_break = min(breaks, key=lambda item: _time_minutes(item["start_time"]))
    timing = next((item for item in period_timings if item.get("period") == start_period), None)
    if timing is None:
        return False
    return _time_minutes(timing["start_time"]) >= _time_minutes(first_break["end_time"])


def has_break_crossing(start_period: int, duration_periods: int, period_timings: Sequence[dict], breaks: Sequence[dict]) -> bool:
    occupied = [
        next((timing for timing in period_timings if timing.get("period") == period), None)
        for period in range(start_period, start_period + duration_periods)
    ]
    if any(timing is None for timing in occupied):
        return bool(breaks)

    activity_start = _time_minutes(occupied[0]["start_time"])
    activity_end = _time_minutes(occupied[-1]["end_time"])
    for break_timing in breaks:
        break_start = _time_minutes(break_timing["start_time"])
        break_end = _time_minutes(break_timing["end_time"])
        if activity_start < break_end and break_start < activity_end:
            return True
    return False


def overlaps_periods(candidate_start: int, candidate_duration: int, existing_start: int, existing_duration: int) -> bool:
    candidate_end = candidate_start + candidate_duration - 1
    existing_end = existing_start + existing_duration - 1
    return candidate_start <= existing_end and existing_start <= candidate_end


def build_slot_times(period_timings: Sequence[dict]) -> dict[int, dict]:
    return {p["period"]: p for p in period_timings}
