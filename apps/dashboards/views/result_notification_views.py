from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect, render

from dashboards.decorators import group_required

from academics.models import Department, Program, Session
from results.models import ResultBatch


@group_required("System Admin")
def result_notifications(request):
    """System Admin UI: pick Department → Program → Session → Semester → Type → Batch, then print."""

    # Read filters
    dept_id = request.GET.get("department") or ""
    program_id = request.GET.get("program") or ""
    session_id = request.GET.get("session") or ""
    semester_no = request.GET.get("semester") or ""
    # UI-friendly type: regular OR reappeared
    ui_type = request.GET.get("result_type") or "regular"
    batch_id = request.GET.get("batch") or ""

    departments = Department.objects.all().order_by("name")

    # Default department: active_department (from context processor) if not selected
    if not dept_id:
        active = getattr(request, "active_department", None)
        if active is None:
            # context processor sets active_department in template context, not on request
            active = request.session.get("active_department_id")
        dept_id = str(active.id) if getattr(active, "id", None) else (str(active) if active else "")

    programs = Program.objects.all().order_by("name")
    if dept_id:
        programs = programs.filter(department_id=dept_id)

    # Build batches queryset first; we will derive dependent filter options from it
    batches = ResultBatch.objects.select_related("program", "session").order_by("-created_at")
    if dept_id:
        batches = batches.filter(program__department_id=dept_id)
    if program_id:
        batches = batches.filter(program_id=program_id)
    if session_id:
        batches = batches.filter(session_id=session_id)

    if ui_type == "regular":
        batches = batches.filter(result_type="regular")
    else:
        batches = batches.filter(result_type__in=["repeat", "improved"])

    # Sessions dropdown should narrow based on Department + Program (+ Type)
    sessions = Session.objects.filter(id__in=batches.values_list("session_id", flat=True)).distinct().order_by("-start_year")

    # Semesters dropdown should narrow based on Department + Program + Session (+ Type)
    semesters = []
    if session_id:
        semesters = (
            batches.values_list("semester_number", flat=True)
            .distinct()
            .order_by("semester_number")
        )

    # Reset stale semester if it doesn't belong to available semesters
    if semester_no and (not session_id or int(semester_no) not in set(semesters)):
        semester_no = ""

    if semester_no:
        batches = batches.filter(semester_number=semester_no)

    # Same idea for batch: reset stale batch_id if it doesn't match current filters.
    if batch_id:
        if not batches.filter(id=batch_id).exists():
            batch_id = ""

    # If after filtering there is exactly one batch, auto-select it to reduce clicks
    if not batch_id and request.GET.get("action") != "print":
        only = list(batches.values_list("id", flat=True)[:2])
        if len(only) == 1:
            batch_id = str(only[0])

    # Action: Generate PDF
    if request.GET.get("action") == "print":
        if not batch_id:
            messages.error(request, "Please select a Result Batch.")
        else:
            return redirect("result_notification_pdf", batch_id=int(batch_id))

    return render(
        request,
        "dashboards/documents/result_notifications.html",
        {
            "departments": departments,
            "dept_id": str(dept_id) if dept_id else "",
            "programs": programs,
            "program_id": str(program_id) if program_id else "",
            "sessions": sessions,
            "session_id": str(session_id) if session_id else "",
            "semesters": semesters,
            "semester_no": str(semester_no) if semester_no else "",
            "ui_type": ui_type,
            "batches": batches,
            "batch_id": str(batch_id) if batch_id else "",
        },
    )
