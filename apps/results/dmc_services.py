from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .hold_services import hold_category_map, hold_label_for_code
from .models import CourseResult, ResultNotificationItem, SemesterResult


@dataclass(frozen=True)
class DMCEligibility:
    """Eligibility result shared by DMC dashboard and PDF endpoints."""

    is_eligible: bool
    reasons: tuple[str, ...] = ()

    @property
    def reason(self) -> str:
        return " ".join(self.reasons)


def _label_list(values: Iterable[str]) -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return ", ".join(cleaned)


def dmc_eligibility_map(
    semester_results: Iterable[SemesterResult],
) -> dict[int, DMCEligibility]:
    """Evaluate whether each semester result may be printed as a DMC.

    A DMC may contain passing or failing grades, but the result must be complete,
    officially released to the student, and free from an active hold.
    """

    result_ids = list(
        dict.fromkeys(
            result.id
            for result in semester_results
            if result is not None and result.id is not None
        )
    )
    if not result_ids:
        return {}

    result_map = {
        result.id: result
        for result in SemesterResult.objects.filter(id__in=result_ids)
        .select_related("batch", "enrollment", "enrollment__student")
    }
    batch_ids = {result.batch_id for result in result_map.values()}

    expected_courses_by_batch: dict[int, dict[int, str]] = defaultdict(dict)
    student_courses: dict[tuple[int, int], set[int]] = defaultdict(set)
    for row in (
        CourseResult.objects.filter(batch_id__in=batch_ids)
        .select_related("course")
        .order_by("batch_id", "course__code", "id")
    ):
        expected_courses_by_batch[row.batch_id].setdefault(
            row.course_id,
            row.course.code,
        )
        student_courses[(row.batch_id, row.enrollment_id)].add(row.course_id)

    released_result_ids = set(
        ResultNotificationItem.objects.filter(
            semester_result_id__in=result_ids,
            hold_status_snapshot=SemesterResult.HOLD_NONE,
        ).values_list("semester_result_id", flat=True)
    )
    hold_categories = hold_category_map(
        result.hold_status for result in result_map.values()
    )

    output: dict[int, DMCEligibility] = {}
    for result_id in result_ids:
        result = result_map.get(result_id)
        if not result:
            output[result_id] = DMCEligibility(
                False,
                ("DMC is not available because the semester result is missing.",),
            )
            continue

        reasons: list[str] = []
        expected_courses = expected_courses_by_batch.get(result.batch_id, {})
        if not expected_courses:
            reasons.append(
                "DMC is not available because no course results are configured for this result batch."
            )
        else:
            available_course_ids = student_courses.get(
                (result.batch_id, result.enrollment_id),
                set(),
            )
            missing_course_ids = [
                course_id
                for course_id in expected_courses
                if course_id not in available_course_ids
            ]
            if missing_course_ids:
                reasons.append(
                    "Missing course result(s): "
                    f"{_label_list(expected_courses[course_id] for course_id in missing_course_ids)}."
                )

        if result.id not in released_result_ids:
            reasons.append("Result has not been officially released for this student.")

        hold_code = result.hold_status or SemesterResult.HOLD_NONE
        if hold_code != SemesterResult.HOLD_NONE:
            hold_label = hold_label_for_code(
                hold_code,
                categories=hold_categories,
            ) or hold_code
            reasons.append(f"Active result hold: {hold_label}.")

        output[result_id] = DMCEligibility(
            not reasons,
            tuple(reasons),
        )

    return output


def evaluate_dmc_eligibility(
    semester_result: SemesterResult,
) -> DMCEligibility:
    """Return whether one semester result may be printed as a DMC."""

    if semester_result is None or semester_result.id is None:
        return DMCEligibility(
            False,
            ("DMC is not available because the semester result is missing.",),
        )
    return dmc_eligibility_map([semester_result])[semester_result.id]
