from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from django.utils.dateparse import parse_date

from dashboards.decorators import group_required
from dashboards.forms import ResultBatchForm
from dashboards.access import (
    assigned_departments_qs,
    deny_department_access,
    get_accessible_batch_or_none,
    is_system_admin,
    restrict_department_queryset,
)
from results.models import ExamType, ResultBatch
from results.models import SemesterResult, CourseResult, ResultNotification, ResultNotificationItem
from academics.models import Program, Session
from results.services import recompute_batch
from results.notification_services import (
    create_result_notification,
    eligible_clearance_results,
    ensure_batch_semester_results,
)


@group_required("System Admin", "Dealing Assistant")
def batch_list(request):
    department_id = (request.GET.get("department") or "").strip()
    program_id = (request.GET.get("program") or "").strip()
    session_id = (request.GET.get("session") or "").strip()
    semester_no = (request.GET.get("semester") or "").strip()
    exam_type_id = (request.GET.get("exam_type") or "").strip()

    base = ResultBatch.objects.select_related("department", "program", "session", "exam_type", "curriculum").prefetch_related("notifications")
    base = restrict_department_queryset(base, request.user, "department")
    batches = base.order_by("-created_at")

    allowed_departments = assigned_departments_qs(request.user)
    if department_id and not allowed_departments.filter(id=department_id).exists():
        department_id = ""

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

    departments = allowed_departments
    programs = Program.objects.all().order_by("name")
    if department_id:
        programs = programs.filter(offerings__department_id=department_id, offerings__is_active=True).distinct()
    else:
        programs = programs.filter(offerings__department__in=departments, offerings__is_active=True).distinct() if departments.exists() else Program.objects.none()

    base_for_sessions = base
    if department_id:
        base_for_sessions = base_for_sessions.filter(department_id=department_id)
    if program_id:
        base_for_sessions = base_for_sessions.filter(program_id=program_id)

    sessions = Session.objects.filter(id__in=base_for_sessions.values_list("session_id", flat=True).distinct()).order_by("-start_year")

    if session_id and not sessions.filter(id=session_id).exists():
        session_id = ""
        semester_no = ""
        batches = base.order_by("-created_at")
        if department_id:
            batches = batches.filter(department_id=department_id)
        if program_id:
            batches = batches.filter(program_id=program_id)

    base_for_semesters = base_for_sessions
    if session_id:
        base_for_semesters = base_for_semesters.filter(session_id=session_id)

    semester_numbers = base_for_semesters.values_list("semester_number", flat=True).distinct().order_by("semester_number")

    base_for_exam_types = base_for_semesters
    if semester_no:
        base_for_exam_types = base_for_exam_types.filter(semester_number=semester_no)

    exam_types = ExamType.objects.filter(id__in=base_for_exam_types.values_list("exam_type_id", flat=True).distinct()).order_by("sort_order", "name")

    return render(request, "dashboards/result_batches/list.html", {
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
    })


@group_required("System Admin", "Dealing Assistant")
def batch_create(request):
    if request.method == "POST":
        form = ResultBatchForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                batch = form.save()
                messages.success(request, "Result batch created successfully.")
                return redirect("admin_batch_detail", pk=batch.pk)
            except IntegrityError:
                messages.error(request, "This batch already exists (same department+program+session+semester+exam type).")
    else:
        initial = {}
        dept_id = (request.GET.get("department") or "").strip()
        allowed_departments = assigned_departments_qs(request.user)
        if dept_id and allowed_departments.filter(id=dept_id).exists():
            initial["department"] = dept_id
        elif not is_system_admin(request.user) and allowed_departments.count() == 1:
            initial["department"] = allowed_departments.first().id
        form = ResultBatchForm(initial=initial, user=request.user)

    return render(request, "dashboards/result_batches/form.html", {"form": form, "title": "Add Result Batch"})


@group_required("System Admin", "Dealing Assistant")
def batch_update(request, pk):
    batch = get_accessible_batch_or_none(request.user, pk)
    if not batch:
        return deny_department_access(request)

    if request.method == "POST":
        form = ResultBatchForm(request.POST, instance=batch, user=request.user)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Result batch updated successfully.")
                return redirect("admin_batch_detail", pk=batch.pk)
            except IntegrityError:
                messages.error(request, "This batch already exists (same department+program+session+semester+exam type).")
    else:
        form = ResultBatchForm(instance=batch, user=request.user)

    return render(request, "dashboards/result_batches/form.html", {"form": form, "title": "Edit Result Batch", "batch": batch})


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
    return render(request, "dashboards/result_batches/confirm_delete.html", {"batch": batch, "delete_blocked": delete_blocked})


@group_required("System Admin", "Dealing Assistant")
def batch_detail(request, pk):
    batch = get_accessible_batch_or_none(request.user, pk)
    if not batch:
        return deny_department_access(request)
    latest_notification = batch.notifications.all().order_by("-created_at").first()
    has_legacy_notification = bool((batch.notification_no or "").strip() or getattr(batch, "notification_date", None))
    max_sem = int(getattr(batch.curriculum, "semester_end", 0) or 0)
    if not max_sem:
        max_sem = int(getattr(batch.program, "semester_end", 0) or 0)
    is_last_semester = bool(max_sem and int(batch.semester_number) == int(max_sem))
    has_marks = batch.course_results.exists()
    return render(request, "dashboards/result_batches/detail.html", {
        "batch": batch,
        "latest_notification": latest_notification,
        "has_legacy_notification": has_legacy_notification,
        "is_last_semester": is_last_semester,
        "max_sem": max_sem,
        "has_marks": has_marks,
    })


@group_required("System Admin", "Dealing Assistant")
def batch_students_holds(request, pk):
    batch = get_accessible_batch_or_none(request.user, pk)
    if not batch:
        return deny_department_access(request)
    enrollment_ids = list(CourseResult.objects.filter(batch=batch).values_list("enrollment_id", flat=True).distinct())
    for eid in enrollment_ids:
        SemesterResult.objects.get_or_create(batch=batch, enrollment_id=eid)
    qs = SemesterResult.objects.filter(batch=batch).select_related("enrollment", "enrollment__student").order_by("enrollment__roll_no")
    if request.method == "POST":
        updated = 0
        for sr in qs:
            status = (request.POST.get(f"hold_status_{sr.id}") or "").strip() or SemesterResult.HOLD_NONE
            note = (request.POST.get(f"hold_note_{sr.id}") or "").strip()
            if status == SemesterResult.HOLD_NONE:
                sr.hold_cleared_at = None
                sr.hold_cleared_by = None
            else:
                sr.hold_cleared_at = None
                sr.hold_cleared_by = None
            if sr.hold_status != status or (sr.hold_note or "") != note:
                sr.hold_status = status
                sr.hold_note = note
                sr.save(update_fields=["hold_status", "hold_note", "hold_cleared_at", "hold_cleared_by"])
                updated += 1
        messages.success(request, f"Saved holds for {updated} student(s).")
        return redirect("admin_batch_students_holds", pk=batch.pk)
    return render(request, "dashboards/result_batches/students_holds.html", {"batch": batch, "rows": qs, "hold_choices": SemesterResult.HOLD_CHOICES})


@group_required("System Admin", "Dealing Assistant")
def batch_notifications(request, pk):
    batch = get_accessible_batch_or_none(request.user, pk)
    if not batch:
        return deny_department_access(request)

    ensure_batch_semester_results(batch)
    notifications = (
        ResultNotification.objects.filter(batch=batch)
        .prefetch_related("items")
        .order_by("notification_date", "created_at", "id")
    )
    full_notification = notifications.filter(
        notification_type=ResultNotification.NotificationType.FULL
    ).first()
    eligible_clearance = eligible_clearance_results(batch)

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        notification_type = {
            "create_full": ResultNotification.NotificationType.FULL,
            "create_clearance": ResultNotification.NotificationType.CLEARANCE,
        }.get(action)
        notification_no = (request.POST.get("notification_no") or "").strip()
        notification_date = parse_date(request.POST.get("notification_date") or "")
        selected_ids = request.POST.getlist("selected_students")

        if not notification_type:
            messages.error(request, "Invalid notification action.")
            return redirect("admin_batch_notifications", pk=batch.pk)

        try:
            notification = create_result_notification(
                batch=batch,
                notification_type=notification_type,
                notification_no=notification_no,
                notification_date=notification_date,
                selected_semester_result_ids=selected_ids,
            )
        except ValidationError as exc:
            if hasattr(exc, "messages"):
                error_message = " ".join(exc.messages)
            else:
                error_message = str(exc)
            messages.error(request, error_message)
            return redirect("admin_batch_notifications", pk=batch.pk)

        messages.success(
            request,
            f"{notification.get_notification_type_display()} created: "
            f"{notification.notification_no} ({notification.items.count()} student(s)).",
        )
        return redirect("admin_batch_notifications", pk=batch.pk)

    return render(
        request,
        "dashboards/result_batches/notifications.html",
        {
            "batch": batch,
            "notifications": notifications,
            "full_notification": full_notification,
            "eligible_clearance": eligible_clearance,
            "eligible_clearance_count": eligible_clearance.count(),
            "today": timezone.localdate(),
        },
    )


@group_required("System Admin")
def batch_notification_delete(request, pk, notification_id):
    batch = get_object_or_404(ResultBatch, pk=pk)
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("admin_batch_notifications", pk=batch.pk)

    notification = get_object_or_404(
        ResultNotification, pk=notification_id, batch=batch
    )
    if (
        notification.notification_type == ResultNotification.NotificationType.FULL
        and batch.notifications.filter(
            notification_type=ResultNotification.NotificationType.CLEARANCE
        ).exists()
    ):
        messages.error(
            request,
            "The Full Notification cannot be deleted after a Clearance Notification exists.",
        )
        return redirect("admin_batch_notifications", pk=batch.pk)

    notification_no = notification.notification_no
    notification.delete()
    messages.success(request, f"Notification deleted: {notification_no}.")
    return redirect("admin_batch_notifications", pk=batch.pk)


@group_required("System Admin", "Dealing Assistant")
def batch_recompute(request, pk):
    batch = get_accessible_batch_or_none(request.user, pk)
    if not batch:
        return deny_department_access(request)
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
