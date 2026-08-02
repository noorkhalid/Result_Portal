from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from academics.models import CurriculumCourse
from students.models import Enrollment

from .hold_services import hold_category_map, hold_label_for_code
from .models import (
    CourseResult,
    GradeScale,
    ResultNotificationItem,
    SemesterResult,
)


@dataclass(frozen=True)
class TranscriptEligibility:
    """Eligibility result used by dashboard and PDF endpoints."""

    is_eligible: bool
    reasons: tuple[str, ...] = ()

    @property
    def reason(self) -> str:
        return " ".join(self.reasons)


def _label_list(values: Iterable[str]) -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return ", ".join(cleaned)


def _fail_letter_set() -> set[str]:
    letters = {
        str(value).strip().upper()
        for value in GradeScale.objects.filter(is_fail=True).values_list(
            "letter_grade", flat=True
        )
        if str(value).strip()
    }
    letters.add("F")
    return letters


def _matches_enrollment(result, enrollment: Enrollment) -> bool:
    batch = result.batch
    return (
        batch.program_id == enrollment.program_id
        and batch.session_id == enrollment.session_id
        and batch.curriculum_id == enrollment.curriculum_id
    )


def transcript_eligibility_map(
    enrollments: Iterable[Enrollment],
) -> dict[int, TranscriptEligibility]:
    """Evaluate multiple enrollments with one shared, database-backed rule."""

    enrollment_ids = list(
        dict.fromkeys(
            enrollment.id
            for enrollment in enrollments
            if enrollment is not None and enrollment.id is not None
        )
    )
    if not enrollment_ids:
        return {}

    enrollment_map = {
        enrollment.id: enrollment
        for enrollment in Enrollment.objects.filter(id__in=enrollment_ids)
        .select_related("curriculum", "program", "session")
    }
    curriculum_ids = {
        enrollment.curriculum_id
        for enrollment in enrollment_map.values()
        if enrollment.curriculum_id
    }

    required_courses_by_curriculum: dict[int, list[CurriculumCourse]] = defaultdict(list)
    all_required_course_ids: set[int] = set()
    for row in (
        CurriculumCourse.objects.filter(curriculum_id__in=curriculum_ids)
        .select_related("course")
        .order_by("curriculum_id", "semester_number", "course__code", "id")
    ):
        required_courses_by_curriculum[row.curriculum_id].append(row)
        all_required_course_ids.add(row.course_id)

    semester_results_by_enrollment: dict[int, list[SemesterResult]] = defaultdict(list)
    all_semester_result_ids: list[int] = []
    all_hold_codes: list[str] = []
    for result in (
        SemesterResult.objects.filter(enrollment_id__in=enrollment_ids)
        .select_related("batch", "batch__exam_type")
        .order_by(
            "enrollment_id",
            "batch__semester_number",
            "batch__created_at",
            "id",
        )
    ):
        enrollment = enrollment_map.get(result.enrollment_id)
        if not enrollment or not _matches_enrollment(result, enrollment):
            continue
        semester_results_by_enrollment[result.enrollment_id].append(result)
        all_semester_result_ids.append(result.id)
        all_hold_codes.append(result.hold_status)

    released_result_ids = set(
        ResultNotificationItem.objects.filter(
            semester_result_id__in=all_semester_result_ids,
            hold_status_snapshot=SemesterResult.HOLD_NONE,
        ).values_list("semester_result_id", flat=True)
    )
    hold_categories = hold_category_map(all_hold_codes)

    latest_attempts_by_enrollment: dict[
        int, dict[tuple[int, int], CourseResult]
    ] = defaultdict(dict)
    if all_required_course_ids:
        for attempt in (
            CourseResult.objects.filter(
                enrollment_id__in=enrollment_ids,
                course_id__in=all_required_course_ids,
            )
            .select_related("course", "batch", "batch__exam_type")
            .order_by(
                "enrollment_id",
                "batch__semester_number",
                "course_id",
                "-batch__created_at",
                "-batch_id",
                "-id",
            )
        ):
            enrollment = enrollment_map.get(attempt.enrollment_id)
            if not enrollment or not _matches_enrollment(attempt, enrollment):
                continue
            key = (int(attempt.batch.semester_number), attempt.course_id)
            latest_attempts_by_enrollment[attempt.enrollment_id].setdefault(
                key, attempt
            )

    fail_letters = _fail_letter_set()
    output: dict[int, TranscriptEligibility] = {}

    for enrollment_id in enrollment_ids:
        enrollment = enrollment_map.get(enrollment_id)
        if not enrollment or not enrollment.curriculum_id:
            output[enrollment_id] = TranscriptEligibility(
                False,
                (
                    "Transcript is not available because the student curriculum is missing.",
                ),
            )
            continue

        curriculum = enrollment.curriculum
        total_semesters = int(curriculum.total_semesters or 0)
        semester_start = int(curriculum.semester_start or 1)
        semester_end = (
            semester_start + total_semesters - 1 if total_semesters else 0
        )
        if total_semesters <= 0 or semester_end <= 0:
            output[enrollment_id] = TranscriptEligibility(
                False,
                (
                    "Transcript is not available because the program duration is not configured.",
                ),
            )
            continue

        reasons: list[str] = []
        required_semesters = set(range(semester_start, semester_end + 1))
        required_courses = [
            row
            for row in required_courses_by_curriculum.get(curriculum.id, [])
            if semester_start <= int(row.semester_number) <= semester_end
        ]
        if not required_courses:
            reasons.append(
                "Transcript is not available because required curriculum courses are not configured."
            )

        semester_results = [
            result
            for result in semester_results_by_enrollment.get(enrollment_id, [])
            if semester_start
            <= int(result.batch.semester_number)
            <= semester_end
        ]
        completed_semesters = {
            int(result.batch.semester_number) for result in semester_results
        }
        missing_semesters = sorted(required_semesters - completed_semesters)
        if missing_semesters:
            reasons.append(
                "Missing semester result(s): "
                f"{_label_list(str(value) for value in missing_semesters)}."
            )

        latest_attempts = latest_attempts_by_enrollment.get(enrollment_id, {})
        missing_course_rows = [
            row
            for row in required_courses
            if (int(row.semester_number), row.course_id) not in latest_attempts
        ]
        if missing_course_rows:
            reasons.append(
                "Missing required course result(s): "
                f"{_label_list(row.course.code for row in missing_course_rows)}."
            )

        unpublished_labels: list[str] = []
        held_labels: list[str] = []
        for result in semester_results:
            batch = result.batch
            batch_label = (
                f"Semester {batch.semester_number} ({batch.exam_type.name})"
            )
            if result.id not in released_result_ids:
                unpublished_labels.append(batch_label)
            if (
                result.hold_status or SemesterResult.HOLD_NONE
            ) != SemesterResult.HOLD_NONE:
                hold_label = hold_label_for_code(
                    result.hold_status,
                    categories=hold_categories,
                ) or result.hold_status
                held_labels.append(f"{batch_label}: {hold_label}")

        if unpublished_labels:
            reasons.append(
                "Result not officially released for: "
                f"{_label_list(unpublished_labels)}."
            )
        if held_labels:
            reasons.append(
                "Active result hold(s): "
                f"{_label_list(held_labels)}."
            )

        failed_courses: list[str] = []
        for row in required_courses:
            attempt = latest_attempts.get(
                (int(row.semester_number), row.course_id)
            )
            if not attempt:
                continue
            letter_grade = (attempt.letter_grade or "").strip().upper()
            grade_point_is_zero = attempt.grade_point is None or attempt.grade_point == 0
            if letter_grade in fail_letters or grade_point_is_zero:
                failed_courses.append(row.course.code)

        if failed_courses:
            reasons.append(
                "Uncleared failed course(s): "
                f"{_label_list(failed_courses)}."
            )

        output[enrollment_id] = TranscriptEligibility(
            not reasons,
            tuple(reasons),
        )

    return output


def evaluate_transcript_eligibility(
    enrollment: Enrollment,
) -> TranscriptEligibility:
    """Return whether one enrollment may receive an academic transcript."""

    if enrollment is None or enrollment.id is None:
        return TranscriptEligibility(
            False,
            ("Transcript is not available because the enrollment is missing.",),
        )
    return transcript_eligibility_map([enrollment])[enrollment.id]
