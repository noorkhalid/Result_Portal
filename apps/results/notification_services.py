from __future__ import annotations

from datetime import date
import re
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from results.hold_services import hold_category_map, hold_label_for_code
from results.models import (
    CourseResult,
    ResultBatch,
    ResultNotification,
    ResultNotificationItem,
    SemesterResult,
)


NOTIFICATION_NUMBER_SUFFIX = "/Results/Exam/GU"
NOTIFICATION_NUMBER_PATTERN = re.compile(
    r"^(?P<sequence>\d{4,})-(?P<year>\d{4})/Results/Exam/GU$",
    re.IGNORECASE,
)


def format_notification_number(sequence: int, year: int) -> str:
    """Return the official notification number format for one yearly sequence."""

    if sequence < 1:
        raise ValueError("Notification sequence must be positive.")
    return f"{sequence:04d}-{year}{NOTIFICATION_NUMBER_SUFFIX}"


def suggest_next_notification_number(notification_date: date) -> str:
    """Suggest the smallest unassigned official number for the date's year.

    Gaps are intentionally reusable. Legacy notification numbers are preserved but
    do not participate in the new yearly sequence.
    """

    if not notification_date:
        raise ValidationError("Notification date is required.")

    year = notification_date.year
    suffix = f"-{year}{NOTIFICATION_NUMBER_SUFFIX}"
    used_sequences: set[int] = set()

    for stored_number in ResultNotification.objects.filter(
        notification_no__iendswith=suffix
    ).values_list("notification_no", flat=True):
        match = NOTIFICATION_NUMBER_PATTERN.fullmatch(stored_number or "")
        if not match or int(match.group("year")) != year:
            continue
        used_sequences.add(int(match.group("sequence")))

    sequence = 1
    while sequence in used_sequences:
        sequence += 1
    return format_notification_number(sequence, year)


def validate_notification_number(notification_no: str, notification_date: date) -> None:
    """Validate a newly issued notification number without touching legacy rows."""

    match = NOTIFICATION_NUMBER_PATTERN.fullmatch(notification_no)
    if not match:
        raise ValidationError(
            'Use the notification number format "0001-YYYY/Results/Exam/GU".'
        )

    sequence = int(match.group("sequence"))
    year = int(match.group("year"))
    if sequence < 1 or match.group("sequence") != f"{sequence:04d}":
        raise ValidationError(
            'Use the notification number format "0001-YYYY/Results/Exam/GU".'
        )
    if year != notification_date.year:
        raise ValidationError(
            "The notification number year must match the Notification Date year."
        )


def ensure_batch_semester_results(batch: ResultBatch) -> None:
    """Ensure every enrollment having course results has a SemesterResult row.

    The existing portal already follows this convention in the notification view.
    Keeping it here makes notification creation safe for future callers too.
    """

    enrollment_ids = CourseResult.objects.filter(batch=batch).values_list(
        "enrollment_id", flat=True
    ).distinct()
    existing_ids = set(
        SemesterResult.objects.filter(
            batch=batch, enrollment_id__in=enrollment_ids
        ).values_list("enrollment_id", flat=True)
    )
    missing = [
        SemesterResult(batch=batch, enrollment_id=enrollment_id)
        for enrollment_id in enrollment_ids
        if enrollment_id not in existing_ids
    ]
    if missing:
        SemesterResult.objects.bulk_create(missing, ignore_conflicts=True)


def eligible_clearance_results(batch: ResultBatch):
    """Return held students who are now clear and have not been cleared before."""

    previously_withheld_ids = ResultNotificationItem.objects.filter(
        notification__batch=batch,
        notification__notification_type=ResultNotification.NotificationType.FULL,
    ).exclude(
        hold_status_snapshot=SemesterResult.HOLD_NONE
    ).values_list(
        "semester_result_id", flat=True
    )

    already_cleared_ids = ResultNotificationItem.objects.filter(
        notification__batch=batch,
        notification__notification_type=ResultNotification.NotificationType.CLEARANCE,
    ).values_list("semester_result_id", flat=True)

    return (
        SemesterResult.objects.filter(
            batch=batch,
            hold_status=SemesterResult.HOLD_NONE,
            id__in=previously_withheld_ids,
        )
        .exclude(id__in=already_cleared_ids)
        .select_related("enrollment", "enrollment__student")
        .order_by("enrollment__roll_no", "id")
        .distinct()
    )


def _normalise_selected_ids(selected_ids: Iterable[int | str] | None) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for raw_value in selected_ids or []:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def create_result_notification(
    *,
    batch: ResultBatch,
    notification_type: str,
    notification_no: str,
    notification_date: date,
    selected_semester_result_ids: Iterable[int | str] | None = None,
) -> ResultNotification:
    """Create a full or clearance notification under one atomic transaction."""

    notification_no = (notification_no or "").strip()
    if not notification_no:
        raise ValidationError("Notification number is required.")
    if not notification_date:
        raise ValidationError("Notification date is required.")
    if notification_type not in ResultNotification.NotificationType.values:
        raise ValidationError("Invalid notification type.")
    validate_notification_number(notification_no, notification_date)

    with transaction.atomic():
        locked_batch = ResultBatch.objects.select_for_update().get(pk=batch.pk)
        ensure_batch_semester_results(locked_batch)

        existing_notification_no = (
            ResultNotification.objects.filter(
                notification_no__iexact=notification_no
            )
            .values_list("notification_no", flat=True)
            .first()
        )
        if existing_notification_no:
            raise ValidationError(
                f'Notification number "{existing_notification_no}" is already assigned.'
            )

        full_exists = ResultNotification.objects.filter(
            batch=locked_batch,
            notification_type=ResultNotification.NotificationType.FULL,
        ).exists()

        if notification_type == ResultNotification.NotificationType.FULL:
            if full_exists:
                raise ValidationError(
                    "A Full Result Notification already exists for this batch."
                )
            semester_results = list(
                SemesterResult.objects.filter(batch=locked_batch)
                .select_related("enrollment", "enrollment__student")
                .order_by("enrollment__roll_no", "id")
            )
            if not semester_results:
                raise ValidationError(
                    "No semester results are available for this batch."
                )

            official_date = (
                locked_batch.official_result_declaration_date or notification_date
            )
            if not locked_batch.official_result_declaration_date:
                ResultBatch.objects.filter(pk=locked_batch.pk).update(
                    official_result_declaration_date=official_date
                )
                locked_batch.official_result_declaration_date = official_date
        else:
            if not full_exists:
                raise ValidationError(
                    "Create the Full Result Notification before a Clearance Notification."
                )

            selected_ids = _normalise_selected_ids(selected_semester_result_ids)
            if not selected_ids:
                raise ValidationError(
                    "Select at least one eligible student for the Clearance Notification."
                )

            eligible_qs = eligible_clearance_results(locked_batch)
            semester_results = list(eligible_qs.filter(id__in=selected_ids))
            eligible_ids = {result.id for result in semester_results}
            invalid_ids = [value for value in selected_ids if value not in eligible_ids]
            if invalid_ids:
                raise ValidationError(
                    "One or more selected students are no longer eligible for clearance. "
                    "Refresh the page and try again."
                )

            official_date = locked_batch.official_result_declaration_date
            if not official_date:
                first_full = (
                    ResultNotification.objects.filter(
                        batch=locked_batch,
                        notification_type=ResultNotification.NotificationType.FULL,
                    )
                    .order_by("created_at", "id")
                    .first()
                )
                official_date = (
                    first_full.declaration_date
                    if first_full
                    else None
                )
            if not official_date:
                raise ValidationError(
                    "The official result declaration date is missing for this batch."
                )

        try:
            notification = ResultNotification.objects.create(
                batch=locked_batch,
                notification_type=notification_type,
                notification_no=notification_no,
                notification_date=notification_date,
                declaration_date=official_date,
            )
        except IntegrityError as exc:
            raise ValidationError(
                f'Notification number "{notification_no}" is already assigned.'
            ) from exc

        hold_categories = hold_category_map(
            semester_result.hold_status for semester_result in semester_results
        )
        items = []
        for semester_result in semester_results:
            hold_code = semester_result.hold_status or SemesterResult.HOLD_NONE
            hold_label = hold_label_for_code(
                hold_code,
                categories=hold_categories,
            )
            items.append(
                ResultNotificationItem(
                    notification=notification,
                    semester_result=semester_result,
                    hold_status_snapshot=hold_code,
                    hold_label_snapshot=hold_label,
                )
            )
        ResultNotificationItem.objects.bulk_create(items)

        return notification
