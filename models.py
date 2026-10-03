from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------
# BASIC TYPES
# ---------------------------------------------------------

ActivityType = Literal[
    "THEORY",
    "LAB",
    "ACTIVITY"
]

ActivityMode = Literal[
    "WHOLE_DIVISION",
    "PARALLEL_BATCH",
    "ROTATIONAL_BATCH"
]


# ---------------------------------------------------------
# ACADEMIC SETTINGS
# ---------------------------------------------------------

class PeriodTiming(BaseModel):
    period: int
    start_time: str
    end_time: str


class BreakTiming(BaseModel):
    name: str
    start_time: str
    end_time: str


class AcademicSettings(BaseModel):
    department: str
    academic_year: str
    semester: str

    working_days: List[str] = Field(
        default_factory=lambda: [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday"
        ]
    )

    periods_per_day: int
    period_timings: List[PeriodTiming]

    breaks: List[BreakTiming] = Field(default_factory=list)


# ---------------------------------------------------------
# BATCH
# ---------------------------------------------------------

class Batch(BaseModel):
    id: str
    name: str
    division: str
    number_of_students: Optional[int] = None


# ---------------------------------------------------------
# SUBJECT
# ---------------------------------------------------------

class Subject(BaseModel):
    id: str
    name: str
    code: str

    activity_type: ActivityType
    activity_mode: ActivityMode

    weekly_periods: int

    faculty_ids: List[str] = Field(default_factory=list)

    important: bool = False

    # Used for shared rotation
    activity_group_id: Optional[str] = None

    # Examples:
    # ["TB1", "TB2", "TB3"]
    applicable_batches: List[str] = Field(default_factory=list)

    # Labs normally require 2 consecutive periods
    duration_periods: int = 1

    # Optional resource requirements
    room_type: Optional[str] = None
    required_room_capacity: Optional[int] = None

    # For lab-specific activities
    required_lab_type: Optional[str] = None


# ---------------------------------------------------------
# FACULTY
# ---------------------------------------------------------

class Faculty(BaseModel):
    id: str
    name: str

    subject_ids: List[str] = Field(default_factory=list)

    qualification: Optional[str] = None

    max_workload: int

    available_days: List[str] = Field(default_factory=list)

    # Example:
    # {
    #   "Monday": [1, 2, 3, 4],
    #   "Tuesday": [1, 2, 5]
    # }
    available_periods: dict[str, List[int]] = Field(
        default_factory=dict
    )

    # Periods where faculty is unavailable
    unavailable_slots: List[str] = Field(
        default_factory=list
    )


# ---------------------------------------------------------
# CLASSROOM
# ---------------------------------------------------------

class Classroom(BaseModel):
    id: str
    name: str

    room_type: str

    capacity: int

    available_days: List[str] = Field(default_factory=list)

    available_periods: dict[str, List[int]] = Field(
        default_factory=dict
    )

    department: Optional[str] = None
    location: Optional[str] = None


# ---------------------------------------------------------
# LABORATORY
# ---------------------------------------------------------

class Laboratory(BaseModel):
    id: str
    name: str

    lab_type: str

    capacity: int

    available_days: List[str] = Field(default_factory=list)

    available_periods: dict[str, List[int]] = Field(
        default_factory=dict
    )

    required_subject_ids: List[str] = Field(
        default_factory=list
    )

    eligible_batches: List[str] = Field(
        default_factory=list
    )

    resources: List[str] = Field(
        default_factory=list
    )


# ---------------------------------------------------------
# EXISTING / FIXED TIMETABLE
# ---------------------------------------------------------

class ExistingActivity(BaseModel):
    id: str

    day: str
    period: int

    duration_periods: int = 1

    subject_id: Optional[str] = None
    faculty_id: Optional[str] = None

    division: Optional[str] = None

    batch_ids: List[str] = Field(default_factory=list)

    classroom_id: Optional[str] = None
    laboratory_id: Optional[str] = None

    activity_type: Optional[ActivityType] = None

    # Always fixed and protected
    fixed: bool = True


# ---------------------------------------------------------
# DIVISION
# ---------------------------------------------------------

class Division(BaseModel):
    id: str
    name: str

    number_of_students: int

    batch_ids: List[str] = Field(default_factory=list)


# ---------------------------------------------------------
# SOLVER CONSTRAINT SETTINGS
# ---------------------------------------------------------

class ConstraintSettings(BaseModel):

    # H9
    labs_need_consecutive_periods: bool = True

    # S1
    prefer_labs_after_first_break: bool = True

    # S2
    prioritize_important_subjects: bool = True

    # S3
    balance_faculty_workload: bool = True

    # S4
    balance_daily_schedule: bool = True

    # S5
    efficient_resource_utilization: bool = True

    # S6
    minimize_unnecessary_gaps: bool = True

    # Maximum solver execution time
    time_limit_seconds: int = 3


# ---------------------------------------------------------
# SOLVER REQUEST
# ---------------------------------------------------------

class SolverRequest(BaseModel):

    settings: AcademicSettings

    division: Division

    batches: List[Batch] = Field(default_factory=list)

    subjects: List[Subject] = Field(default_factory=list)

    faculty: List[Faculty] = Field(default_factory=list)

    classrooms: List[Classroom] = Field(default_factory=list)

    laboratories: List[Laboratory] = Field(default_factory=list)

    # Existing timetable must remain fixed
    existing_timetable: List[ExistingActivity] = Field(
        default_factory=list
    )

    constraints: ConstraintSettings = Field(
        default_factory=ConstraintSettings
    )


# ---------------------------------------------------------
# GENERATED ACTIVITY
# ---------------------------------------------------------

class GeneratedActivity(BaseModel):

    subject_id: str
    subject_name: str

    day: str
    period: int

    duration_periods: int

    faculty_id: Optional[str] = None

    division: str

    batch_ids: List[str] = Field(default_factory=list)

    classroom_id: Optional[str] = None
    laboratory_id: Optional[str] = None

    activity_type: ActivityType
    activity_mode: ActivityMode


# ---------------------------------------------------------
# SOLVER RESULT
# ---------------------------------------------------------

class SolverStatistics(BaseModel):

    requested_periods: int = 0
    scheduled_periods: int = 0
    free_periods: int = 0

    solver_time_seconds: float = 0.0


class SolverResult(BaseModel):

    status: str

    solve_time_seconds: float = 0.0

    activities: List[GeneratedActivity] = Field(
        default_factory=list
    )

    warnings: List[str] = Field(
        default_factory=list
    )

    violations: List[str] = Field(
        default_factory=list
    )

    statistics: SolverStatistics = Field(
        default_factory=SolverStatistics
    )