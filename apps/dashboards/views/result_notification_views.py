from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect, render

from dashboards.decorators import group_required
from dashboards.access import assigned_departments_qs, restrict_department_queryset

from academics.models import Program, Session
from results.models import ExamType, ResultBatch


@group_required("System Admin", "Dealing Assistant")
def result_notifications(request):
    dept_id = request.GET.get("department") or ""
    program_id = request.GET.get("program") or ""
    session_id = request.GET.get("session") or ""
    semester_no = request.GET.get("semester") or ""
    exam_type_id = request.GET.get("exam_type") or ""
    batch_id = request.GET.get("batch") or ""

    departments = assigned_departments_qs(request.user)
    if dept_id and not departments.filter(id=dept_id).exists():
        dept_id = ""

    if not dept_id:
        active = getattr(request, "active_department", None)
        if active and departments.filter(id=getattr(active, "id", None)).exists():
            dept_id = str(active.id)

    programs = Program.objects.all().order_by("name")
    if dept_id:
        programs = programs.filter(offerings__department_id=dept_id, offerings__is_active=True).distinct()
    else:
        programs = programs.filter(offerings__department__in=departments, offerings__is_active=True).distinct() if departments.exists() else Program.objects.none()

    batches = ResultBatch.objects.select_related("program", "session", "exam_type", "department").order_by("-created_at")
    batches = restrict_department_queryset(batches, request.user, "department")
    if dept_id:
        batches = batches.filter(department_id=dept_id)
    if program_id:
        batches = batches.filter(program_id=program_id)
    if session_id:
        batches = batches.filter(session_id=session_id)
    if exam_type_id:
        batches = batches.filter(exam_type_id=exam_type_id)

    sessions = Session.objects.filter(id__in=batches.values_list("session_id", flat=True)).distinct().order_by("-start_year")
    semesters = []
    if session_id:
        semesters = batches.values_list("semester_number", flat=True).distinct().order_by("semester_number")
    if semester_no and (not session_id or int(semester_no) not in set(semesters)):
        semester_no = ""
    if semester_no:
        batches = batches.filter(semester_number=semester_no)

    exam_types = ExamType.objects.filter(id__in=batches.values_list("exam_type_id", flat=True).distinct()).order_by("sort_order", "name")
    if batch_id and not batches.filter(id=batch_id).exists():
        batch_id = ""
    if not batch_id and request.GET.get("action") != "print":
        only = list(batches.values_list("id", flat=True)[:2])
        if len(only) == 1:
            batch_id = str(only[0])

    if request.GET.get("action") == "print":
        if not batch_id:
            messages.error(request, "Please select a Result Batch.")
        else:
            return redirect("result_notification_pdf", batch_id=int(batch_id))

    return render(request, "dashboards/documents/result_notifications.html", {
        "departments": departments,
        "dept_id": str(dept_id) if dept_id else "",
        "programs": programs,
        "program_id": str(program_id) if program_id else "",
        "sessions": sessions,
        "session_id": str(session_id) if session_id else "",
        "semesters": semesters,
        "semester_no": str(semester_no) if semester_no else "",
        "exam_types": exam_types,
        "exam_type_id": str(exam_type_id) if exam_type_id else "",
        "batches": batches,
        "batch_id": str(batch_id) if batch_id else "",
    })
