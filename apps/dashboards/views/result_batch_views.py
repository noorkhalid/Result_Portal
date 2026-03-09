from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError

from dashboards.decorators import group_required
from dashboards.forms import ResultBatchForm
from results.models import ExamType, ResultBatch
from results.models import SemesterResult, CourseResult, ResultNotification, ResultNotificationItem
from academics.models import Department, Program, Session
from results.services import recompute_batch


@group_required("System Admin")
def batch_list(request):
    department_id = (request.GET.get("department") or "").strip()
    program_id = (request.GET.get("program") or "").strip()
    session_id = (request.GET.get("session") or "").strip()
    semester_no = (request.GET.get("semester") or "").strip()
    exam_type_id = (request.GET.get("exam_type") or "").strip()

    base = (
        ResultBatch.objects.select_related("department", "program", "session")
        .prefetch_related("notifications")
        .all()
    )
    batches = base.order_by("-created_at")

    if department_id:
        batches = batches.filter(department_id=department_id)

    if program_id:
        batches = batches.filter(program_id=program_id)
    if session_id:
        batches = batches.filter(session_id=session_id)
    if semester_no:
        batches = batches.filter(semester_number=semester_no)
    if exam_type_id:
        batches = batches.filter(exam_type_id=exam_type_id)

    departments = Department.objects.all().order_by("name")
    programs = Program.objects.all().order_by("name")

    if department_id:
        programs = programs.filter(offerings__department_id=department_id, offerings__is_active=True).distinct()

    # Dependent filter options (narrow based on selected values)
    base_for_sessions = base
    if department_id:
        base_for_sessions = base_for_sessions.filter(department_id=department_id)
    if program_id:
        base_for_sessions = base_for_sessions.filter(program_id=program_id)

    # sessions should narrow when program selected
    sessions = Session.objects.filter(
        id__in=base_for_sessions.values_list("session_id", flat=True).distinct()
    ).order_by("-start_year")

    # If selected session is not valid for this program, reset it (and semester)
    if session_id and not sessions.filter(id=session_id).exists():
        session_id = ""
        semester_no = ""
        # also reset batches filter
        batches = base.order_by("-created_at")
        if department_id:
            batches = batches.filter(department_id=department_id)
        if program_id:
            batches = batches.filter(program_id=program_id)

    base_for_semesters = base_for_sessions
    if session_id:
        base_for_semesters = base_for_semesters.filter(session_id=session_id)

    # semester numbers should narrow based on program (+ session)
    semester_numbers = (
        base_for_semesters.values_list("semester_number", flat=True).distinct().order_by("semester_number")
    )

    base_for_exam_types = base_for_semesters
    if semester_no:
        base_for_exam_types = base_for_exam_types.filter(semester_number=semester_no)

    exam_types = ExamType.objects.filter(
        id__in=base_for_exam_types.values_list("exam_type_id", flat=True).distinct()
    ).order_by("sort_order", "name")

    return render(
        request,
        "dashboards/result_batches/list.html",
        {
            "batches": batches,
            "departments": departments,
            "programs": programs,
            "sessions": sessions,
            "semester_numbers": semester_numbers,
            "exam_types": exam_types,
            "department_id": department_id,
            "program_id": program_id,
            "session_id": session_id,
            "semester_no": semester_no,
            "exam_type_id": exam_type_id,
        },
    )


@group_required("System Admin")
def batch_create(request):
    if request.method == "POST":
        form = ResultBatchForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Result batch created successfully.")
                return redirect("admin_batch_list")
            except IntegrityError:
                messages.error(request, "This batch already exists (program+session+semester+exam type).")
    else:
        # Allow preselecting department (and thus narrowing programs) via GET
        initial = {}
        dept_id = (request.GET.get("department") or "").strip()
        if dept_id:
            initial["department"] = dept_id
        form = ResultBatchForm(initial=initial)

    return render(
        request,
        "dashboards/result_batches/form.html",
        {"form": form, "title": "Add Result Batch"},
    )


@group_required("System Admin")
def batch_update(request, pk):
    batch = get_object_or_404(ResultBatch, pk=pk)

    if request.method == "POST":
        form = ResultBatchForm(request.POST, instance=batch)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Result batch updated successfully.")
                return redirect("admin_batch_list")
            except IntegrityError:
                messages.error(request, "This batch already exists (program+session+semester+exam type).")
    else:
        form = ResultBatchForm(instance=batch)

    return render(
        request,
        "dashboards/result_batches/form.html",
        {"form": form, "title": "Edit Result Batch", "batch": batch},
    )


@group_required("System Admin")
def batch_delete(request, pk):
    batch = get_object_or_404(ResultBatch, pk=pk)

    delete_blocked = batch.course_results.exists() or batch.semester_results.exists()

    if request.method == "POST":
        if delete_blocked:
            messages.error(request, "Cannot delete: results exist in this batch.")
            return redirect("admin_batch_list")

        batch.delete()
        messages.success(request, "Result batch deleted successfully.")
        return redirect("admin_batch_list")

    return render(
        request,
        "dashboards/result_batches/confirm_delete.html",
        {"batch": batch, "delete_blocked": delete_blocked},
    )


@group_required("System Admin")
def batch_detail(request, pk):
    batch = get_object_or_404(ResultBatch, pk=pk)

    # Notification display should come from ResultNotification history.
    # We show the latest notification if present; otherwise we fall back to legacy
    # batch.notification_no/date (for old data).
    latest_notification = batch.notifications.all().order_by("-created_at").first()
    has_legacy_notification = bool(
        (batch.notification_no or "").strip() or getattr(batch, "notification_date", None)
    )

    # "Last semester" for Transcript availability is defined by the semester span.
    # Prefer the curriculum snapshot if present.
    max_sem = int(getattr(batch.curriculum, "semester_end", 0) or 0)
    if not max_sem:
        max_sem = int(getattr(batch.program, "semester_end", 0) or 0)

    is_last_semester = bool(max_sem and int(batch.semester_number) == int(max_sem))
    has_marks = batch.course_results.exists()
    return render(
        request,
        "dashboards/result_batches/detail.html",
        {
            "batch": batch,
            "latest_notification": latest_notification,
            "has_legacy_notification": has_legacy_notification,
            "is_last_semester": is_last_semester,
            "max_sem": max_sem,
            "has_marks": has_marks,
        },
    )


@group_required("System Admin")
def batch_students_holds(request, pk):
    """Manage per-student Result Hold (RL) statuses for a batch."""

    batch = get_object_or_404(ResultBatch, pk=pk)

    # Ensure SemesterResult rows exist for any enrollment that has marks in this batch.
    enrollment_ids = list(
        CourseResult.objects.filter(batch=batch)
        .values_list("enrollment_id", flat=True)
        .distinct()
    )

    for eid in enrollment_ids:
        SemesterResult.objects.get_or_create(batch=batch, enrollment_id=eid)

    qs = (
        SemesterResult.objects.filter(batch=batch)
        .select_related("enrollment", "enrollment__student")
        .order_by("enrollment__roll_no")
    )

    if request.method == "POST":
        updated = 0
        for sr in qs:
            status = (request.POST.get(f"hold_status_{sr.id}") or "").strip() or SemesterResult.HOLD_NONE
            note = (request.POST.get(f"hold_note_{sr.id}") or "").strip()

            # Clear metadata if moving to NONE
            if status == SemesterResult.HOLD_NONE:
                sr.hold_cleared_at = None
                sr.hold_cleared_by = None
            else:
                # If previously held and now still held, keep cleared info empty.
                sr.hold_cleared_at = None
                sr.hold_cleared_by = None

            if sr.hold_status != status or (sr.hold_note or "") != note:
                sr.hold_status = status
                sr.hold_note = note
                sr.save(update_fields=["hold_status", "hold_note", "hold_cleared_at", "hold_cleared_by"])
                updated += 1

        messages.success(request, f"Saved holds for {updated} student(s).")
        return redirect("admin_batch_students_holds", pk=batch.pk)

    return render(
        request,
        "dashboards/result_batches/students_holds.html",
        {
            "batch": batch,
            "rows": qs,
            "hold_choices": SemesterResult.HOLD_CHOICES,
        },
    )


@group_required("System Admin")
def batch_notifications(request, pk):
    """Create and list notifications for a batch (initial + clearance)."""

    batch = get_object_or_404(ResultBatch, pk=pk)

    # Ensure SemesterResult rows exist when marks exist.
    enrollment_ids = list(
        CourseResult.objects.filter(batch=batch)
        .values_list("enrollment_id", flat=True)
        .distinct()
    )
    for eid in enrollment_ids:
        SemesterResult.objects.get_or_create(batch=batch, enrollment_id=eid)

    notifications = ResultNotification.objects.filter(batch=batch).order_by("-created_at")
    first_notification = notifications.order_by("created_at").first()

    # Eligible for clearance: currently NONE, previously RL in any notification, and not yet notified as NONE.
    eligible_clearance = SemesterResult.objects.filter(batch=batch, hold_status=SemesterResult.HOLD_NONE)
    eligible_clearance = eligible_clearance.filter(notification_items__hold_status_snapshot__in=[SemesterResult.HOLD_DUES, SemesterResult.HOLD_DOCUMENTS]).exclude(
        notification_items__hold_status_snapshot=SemesterResult.HOLD_NONE
    ).distinct()

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        notification_no = (request.POST.get("notification_no") or "").strip()
        notification_date = request.POST.get("notification_date")

        if not notification_no or not notification_date:
            messages.error(request, "Notification number and date are required.")
            return redirect("admin_batch_notifications", pk=batch.pk)

        # Declaration date: fixed from first notification; otherwise equals current notification date.
        declaration_date = first_notification.declaration_date if first_notification else notification_date

        notif = ResultNotification.objects.create(
            batch=batch,
            notification_no=notification_no,
            notification_date=notification_date,
            declaration_date=declaration_date,
        )

        if action == "create_clearance":
            srs = list(eligible_clearance)
            if not srs:
                notif.delete()
                messages.error(request, "No cleared students found for a clearance notification.")
                return redirect("admin_batch_notifications", pk=batch.pk)
        else:
            # Default: create full notification
            srs = list(SemesterResult.objects.filter(batch=batch))

        items = []
        for sr in srs:
            items.append(
                ResultNotificationItem(
                    notification=notif,
                    semester_result=sr,
                    hold_status_snapshot=sr.hold_status,
                )
            )
        ResultNotificationItem.objects.bulk_create(items)

        messages.success(request, f"Notification created: {notif.notification_no} ({len(items)} student(s)).")
        return redirect("admin_batch_notifications", pk=batch.pk)

    return render(
        request,
        "dashboards/result_batches/notifications.html",
        {
            "batch": batch,
            "notifications": notifications,
            "eligible_clearance_count": eligible_clearance.count(),
        },
    )


@group_required("System Admin")
def batch_notification_delete(request, pk, notification_id):
    """Delete a single result notification belonging to a batch (POST-only)."""

    batch = get_object_or_404(ResultBatch, pk=pk)

    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("admin_batch_notifications", pk=batch.pk)

    notif = get_object_or_404(ResultNotification, pk=notification_id, batch=batch)

    # Safety: if you ever want to block deletion of declared notifications, uncomment:
    # if notif.declaration_date:
    #     messages.error(request, "Declared notifications cannot be deleted.")
    #     return redirect("admin_batch_notifications", pk=batch.pk)

    notif_no = notif.notification_no
    notif.delete()
    messages.success(request, f"Notification deleted: {notif_no}.")
    return redirect("admin_batch_notifications", pk=batch.pk)


@group_required("System Admin")
def batch_recompute(request, pk):
    """Recompute GPA/CGPA for a result batch.

    This is needed when marks were imported without ticking the "Recompute" option.
    We keep this action POST-only to avoid accidental recomputation by link clicks.
    """
    batch = get_object_or_404(ResultBatch, pk=pk)

    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("admin_batch_detail", pk=batch.pk)

    if not batch.course_results.exists():
        messages.error(request, "Cannot recompute: no marks exist in this batch.")
        return redirect("admin_batch_detail", pk=batch.pk)

    try:
        recompute_batch(batch)
    except Exception as e:
        messages.error(request, f"Recompute failed: {e}")
        return redirect("admin_batch_detail", pk=batch.pk)

    messages.success(request, "GPA / CGPA recomputed successfully for this batch.")
    return redirect("admin_batch_detail", pk=batch.pk)

