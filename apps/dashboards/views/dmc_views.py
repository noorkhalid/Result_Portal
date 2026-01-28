from __future__ import annotations

from django.contrib import messages
from django.db.models import F
from django.shortcuts import redirect, render

from dashboards.decorators import group_required

from academics.models import Department, Program, Session
from results.models import ResultBatch, SemesterResult


@group_required("System Admin", "Document Generator", "Controller")
def dmc_single(request):
    """UI: pick Department → Program → Session → Semester → Type → Batch → Student, then print DMC."""

    # Read filters
    dept_id = request.GET.get("department") or ""
    program_id = request.GET.get("program") or ""
    session_id = request.GET.get("session") or ""
    semester_no = request.GET.get("semester") or ""
    ui_type = request.GET.get("result_type") or "regular"  # regular OR reappeared
    batch_id = request.GET.get("batch") or ""
    enrollment_id = request.GET.get("enrollment") or ""

    # If user comes from Result Batch list, they may only send ?batch=<id>
    # In that case, prefill the other filters from the batch.
    if batch_id and not any([dept_id, program_id, session_id, semester_no]):
        b = ResultBatch.objects.select_related("program", "session", "program__department").filter(id=batch_id).first()
        if b:
            dept_id = str(b.program.department_id)
            program_id = str(b.program_id)
            session_id = str(b.session_id)
            semester_no = str(b.semester_number)
            ui_type = "regular" if b.result_type == "regular" else "reappeared"

    departments = Department.objects.all().order_by("name")

    # Default department: active_department if not selected
    if not dept_id:
        active = getattr(request, "active_department", None)
        if active is None:
            active = request.session.get("active_department_id")
        dept_id = str(active.id) if getattr(active, "id", None) else (str(active) if active else "")

    programs = Program.objects.all().order_by("name")
    if dept_id:
        programs = programs.filter(department_id=dept_id)

    # Base batches queryset from which we derive dependent options.
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
        # UI merges repeat + improved
        batches = batches.filter(result_type__in=["repeat", "improved"])

    sessions = (
        Session.objects.filter(id__in=batches.values_list("session_id", flat=True))
        .distinct()
        .order_by("-start_year")
    )

    semesters = []
    if session_id:
        semesters = (
            batches.values_list("semester_number", flat=True)
            .distinct()
            .order_by("semester_number")
        )

    if semester_no and (not session_id or int(semester_no) not in set(semesters)):
        semester_no = ""

    if semester_no:
        batches = batches.filter(semester_number=semester_no)

    if batch_id and not batches.filter(id=batch_id).exists():
        batch_id = ""
        enrollment_id = ""

    # Auto-select a single batch if it is the only match (unless printing)
    if not batch_id and request.GET.get("action") != "print":
        only = list(batches.values_list("id", flat=True)[:2])
        if len(only) == 1:
            batch_id = str(only[0])

    # Students dropdown: only after selecting a batch
    students = []
    if batch_id:
        students = (
            SemesterResult.objects.filter(batch_id=batch_id)
            .select_related("enrollment", "enrollment__student")
            .annotate(
                roll=F("enrollment__roll_no"),
                reg=F("enrollment__student__registration_no"),
                name=F("enrollment__student__name"),
            )
            .order_by("roll")
        )

        # If there is only one student result, auto-select it
        if not enrollment_id and request.GET.get("action") != "print":
            only_enr = list(students.values_list("enrollment_id", flat=True)[:2])
            if len(only_enr) == 1:
                enrollment_id = str(only_enr[0])

        # Reset stale enrollment selection
        if enrollment_id and not students.filter(enrollment_id=enrollment_id).exists():
            enrollment_id = ""

    # Action: print
    if request.GET.get("action") == "print":
        if not batch_id:
            messages.error(request, "Please select a Result Batch.")
        elif not enrollment_id:
            messages.error(request, "Please select a Student.")
        else:
            return redirect(
                "dmc_single_pdf",
                batch_id=int(batch_id),
                enrollment_id=int(enrollment_id),
            )

    return render(
        request,
        "dashboards/documents/dmc_single.html",
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
            "students": students,
            "enrollment_id": str(enrollment_id) if enrollment_id else "",
        },
    )
