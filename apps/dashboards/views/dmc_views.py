from __future__ import annotations

from django.contrib import messages
from django.db.models import F
from django.shortcuts import redirect, render, get_object_or_404

from dashboards.decorators import group_required
from dashboards.access import assigned_departments_qs, restrict_department_queryset

from academics.models import Department, Program, Session
from results.dmc_services import dmc_eligibility_map
from results.models import ExamType, ResultBatch, SemesterResult


@group_required("System Admin", "Document Generator", "Controller", "Dealing Assistant")
def dmc_single(request):
    """UI: pick Department → Program → Session → Semester → Type → Batch → Student, then print DMC."""

    # Read filters
    dept_id = request.GET.get("department") or ""
    program_id = request.GET.get("program") or ""
    session_id = request.GET.get("session") or ""
    semester_no = request.GET.get("semester") or ""
    exam_type_id = request.GET.get("exam_type") or ""
    batch_id = request.GET.get("batch") or ""
    enrollment_id = request.GET.get("enrollment") or ""

    # If user comes from Result Batch list, they may only send ?batch=<id>
    # In that case, prefill the other filters from the batch.
    if batch_id and not any([dept_id, program_id, session_id, semester_no]):
        b = ResultBatch.objects.select_related("program", "session", "exam_type").filter(id=batch_id).first()
        if b:
            dept_id = str(b.department_id)
            program_id = str(b.program_id)
            session_id = str(b.session_id)
            semester_no = str(b.semester_number)
            exam_type_id = str(b.exam_type_id)

    departments = assigned_departments_qs(request.user) if request.user.groups.filter(name="Dealing Assistant").exists() and not (request.user.is_superuser or request.user.groups.filter(name="System Admin").exists()) else Department.objects.all().order_by("name")

    # Default department: active_department if not selected
    if not dept_id:
        active = getattr(request, "active_department", None)
        if active is None:
            active = request.session.get("active_department_id")
        dept_id = str(active.id) if getattr(active, "id", None) else (str(active) if active else "")

    programs = Program.objects.all().order_by("name")
    if dept_id:
        programs = programs.filter(offerings__department_id=dept_id, offerings__is_active=True).distinct()

    # Base batches queryset from which we derive dependent options.
    batches = ResultBatch.objects.select_related("program", "session", "exam_type").order_by("-created_at")
    batches = restrict_department_queryset(batches, request.user, "department")
    if dept_id:
        batches = batches.filter(department_id=dept_id)
    if program_id:
        batches = batches.filter(program_id=program_id)
    if session_id:
        batches = batches.filter(session_id=session_id)

    # Exam type filter (optional)
    if exam_type_id:
        batches = batches.filter(exam_type_id=exam_type_id)

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

    # Dependent exam types list (after dept/program/session/semester narrowing)
    exam_types = ExamType.objects.filter(
        id__in=batches.values_list("exam_type_id", flat=True).distinct()
    ).order_by("sort_order", "name")

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
    eligibility_map = {}
    selected_eligibility = None
    if batch_id:
        students = list(
            SemesterResult.objects.filter(batch_id=batch_id)
            .select_related("enrollment", "enrollment__student")
            .annotate(
                roll=F("enrollment__roll_no"),
                reg=F("enrollment__student__registration_no"),
                name=F("enrollment__student__name"),
            )
            .order_by("roll")
        )
        eligibility_map = dmc_eligibility_map(students)

        # If there is only one student result, auto-select it
        if not enrollment_id and request.GET.get("action") != "print":
            only_enr = [result.enrollment_id for result in students][:2]
            if len(only_enr) == 1:
                enrollment_id = str(only_enr[0])

        # Reset stale enrollment selection
        selected_result = next(
            (
                result
                for result in students
                if str(result.enrollment_id) == str(enrollment_id)
            ),
            None,
        )
        if enrollment_id and selected_result is None:
            enrollment_id = ""
        elif selected_result is not None:
            selected_eligibility = eligibility_map.get(selected_result.id)

    # Action: print
    if request.GET.get("action") == "print":
        if not batch_id:
            messages.error(request, "Please select a Result Batch.")
        elif not enrollment_id:
            messages.error(request, "Please select a Student.")
        elif selected_eligibility and not selected_eligibility.is_eligible:
            messages.error(
                request,
                f"DMC is not available: {selected_eligibility.reason}",
            )
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
            "exam_types": exam_types,
            "exam_type_id": str(exam_type_id) if exam_type_id else "",
            "batches": batches,
            "batch_id": str(batch_id) if batch_id else "",
            "students": students,
            "eligibility_map": eligibility_map,
            "enrollment_id": str(enrollment_id) if enrollment_id else "",
            "selected_eligibility": selected_eligibility,
        },
    )


@group_required("System Admin", "Document Generator", "Controller", "Dealing Assistant")
def dmc_selected(request, batch_id):
    """UI: choose one or more students from a batch, then print one combined DMC PDF.

    The PDF generation is handled by results.dmc_batch_pdf using selected enrollment IDs.
    Selecting one student prints a single DMC; selecting many prints multiple DMCs.
    """

    batch = get_object_or_404(
        ResultBatch.objects.select_related("department", "program", "session", "exam_type"),
        id=batch_id,
    )

    allowed_batches = restrict_department_queryset(ResultBatch.objects.all(), request.user, "department")
    if not allowed_batches.filter(id=batch.id).exists():
        messages.error(request, "You do not have permission to access that result batch.")
        return redirect("dashboard")

    students = list(
        SemesterResult.objects.filter(batch=batch)
        .select_related("enrollment", "enrollment__student")
        .annotate(
            roll=F("enrollment__roll_no"),
            reg=F("enrollment__student__registration_no"),
            name=F("enrollment__student__name"),
            father_name=F("enrollment__student__father_name"),
        )
        .order_by("roll")
    )
    eligibility_map = dmc_eligibility_map(students)

    if request.method == "POST":
        selected_ids = request.POST.getlist("enrollment_ids")
        selected_ids = [x for x in selected_ids if x.isdigit()]

        if not selected_ids:
            messages.error(request, "Please select at least one student.")
        else:
            student_map = {str(result.enrollment_id): result for result in students}
            invalid_ids = [value for value in selected_ids if value not in student_map]
            if invalid_ids:
                messages.error(request, "One or more selected students do not belong to this result batch.")
            else:
                ineligible_results = [
                    student_map[value]
                    for value in selected_ids
                    if not eligibility_map[student_map[value].id].is_eligible
                ]
                if ineligible_results:
                    details = "; ".join(
                        f"{result.enrollment.roll_no}: {eligibility_map[result.id].reason}"
                        for result in ineligible_results
                    )
                    messages.error(
                        request,
                        f"DMC is not available for the selected student(s): {details}",
                    )
                else:
                    return redirect(
                        f"/results/dmc/{batch.id}/pdf/?enrollments={','.join(selected_ids)}"
                    )

    return render(
        request,
        "dashboards/documents/dmc_selected.html",
        {
            "batch": batch,
            "students": students,
            "eligibility_map": eligibility_map,
        },
    )
