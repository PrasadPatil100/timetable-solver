from __future__ import annotations

from typing import Iterable, List

from models import GeneratedActivity


def convert_to_activities(raw_candidates: Iterable[dict], day_names: list[str]) -> List[GeneratedActivity]:
    activities: List[GeneratedActivity] = []
    for candidate in raw_candidates:
        activities.append(
            GeneratedActivity(
                subject_id=candidate["subject_id"],
                subject_name=candidate["subject_name"],
                day=candidate["day"],
                period=candidate["period"],
                duration_periods=candidate["duration_periods"],
                faculty_id=candidate["faculty_id"],
                division=candidate["division"],
                batch_ids=list(candidate.get("batch_ids", [])),
                classroom_id=candidate.get("classroom_id"),
                laboratory_id=candidate.get("laboratory_id"),
                activity_type=candidate["activity_type"],
                activity_mode=candidate["activity_mode"],
            )
        )
    return activities
