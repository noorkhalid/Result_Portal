from __future__ import annotations

from django.contrib import messages
from django.db.models import F
from django.shortcuts import redirect, render, get_object_or_404

from dashboards.decorators import group_required
from dashboards.access import assigned_departments_qs, restrict_department_queryset
from academics.models import Department, Program, Session, Curriculum
from results.models import ResultBatch, SemesterResult
from results.transcript_services import transcript_eligibility_map
from students.models import Enrollment


def _semester_span_for(program_id: str | int, session_id: str | int) -> tuple[int, int, int]:
    """Return (semester_start, semester_end, total_semesters) for program+session."""

    cur = (
        Curriculum.objects.filter(program_id=program_id, session_id=session_id)
        .only("total_semesters", "semester_start")
        .first()
    )
    if cur:
        total = int(cur.total_semesters or 0)
        start = int(getattr(cur, "semester_start", 1) or 1)
        end = start + total - 1 if total > 0 else 0
        return (start, end, total)

    program = Program.objects.filter(id=program_id).only("total_semesters", "semester_start").first()
    if not program:
        return (1, 0, 0)
    total = int(program.total_semesters or 0)
    start = int(getattr(program, "semester_start", 1) or 1)
    end = start + total - 1 if total > 0 else 0
    return (start, end, total)


@group_required("System Admin", "Document Generator", "Controller", "Dealing Assistant")
def transcript_single(request):
    """UI: pick Department → Program → Session → (auto last semester batch) → Student, then print Transcript.

    Rule:
      Transcript availability is decided by the shared transcript eligibility
      service used by both dashboard and direct PDF endpoints.

    Entry point:
      From Result Batch detail page we expect: ?batch=<id>
      (button exists only for last semester batch).
    """

    dept_id = request.GET.get("department") or ""
    program_id = request.GET.get("program") or ""
    session_id = request.GET.get("session") or ""
    batch_id = request.GET.get("batch") or ""
    enrollment_id = request.GET.get("enrollment") or ""

    # Prefill from batch if user comes with only ?batch=
    if batch_id and not any([dept_id, program_id, session_id]):
        b = (
            ResultBatch.objects.select_related("program", "session")
            .filter(id=batch_id)
            .first()
        )
        if b:
            dept_id = str(b.department_id)
            program_id = str(b.program_id)
            session_id = str(b.session_id)

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

    # Base batches for dependent filters
    batches_qs = ResultBatch.objects.select_related("program", "session").order_by("-created_at")
    batches_qs = restrict_department_queryset(batches_qs, request.user, "department")
    if dept_id:
        batches_qs = batches_qs.filter(department_id=dept_id)
    if program_id:
        batches_qs = batches_qs.filter(program_id=program_id)
    if session_id:
        batches_qs = batches_qs.filter(session_id=session_id)

    sessions = (
        Session.objects.filter(id__in=batches_qs.values_list("session_id", flat=True))
        .distinct()
        .order_by("-start_year")
    )

    sem_start = 0
    sem_end = 0
    total_semesters = 0
    last_sem_batches = ResultBatch.objects.none()
    if program_id and session_id:
        sem_start, sem_end, total_semesters = _semester_span_for(program_id, session_id)
        if sem_end:
            last_sem_batches = batches_qs.filter(semester_number=sem_end)

    # If stale session selection, reset
    if session_id and not sessions.filter(id=session_id).exists():
        session_id = ""
        batch_id = ""
        enrollment_id = ""
        sem_start = 0
        sem_end = 0
        total_semesters = 0
        last_sem_batches = ResultBatch.objects.none()

    # Ensure batch_id is within last semester batches
    if batch_id and last_sem_batches.exists() and not last_sem_batches.filter(id=batch_id).exists():
        batch_id = ""
        enrollment_id = ""

    # Auto-select single last-semester batch if only one
    if not batch_id and request.GET.get("action") != "print":
        only = list(last_sem_batches.values_list("id", flat=True)[:2])
        if len(only) == 1:
            batch_id = str(only[0])

    students = []
    eligibility_map = {}
    selected_eligibility = None

    if batch_id:
        # Students shown from this last-semester batch
        students_qs = (
            SemesterResult.objects.filter(batch_id=batch_id)
            .select_related("enrollment", "enrollment__student")
            .annotate(
                roll=F("enrollment__roll_no"),
                reg=F("enrollment__student__registration_no"),
                name=F("enrollment__student__name"),
            )
            .order_by("roll")
        )

        students = list(students_qs)

        # Use the same eligibility rule that protects the PDF endpoint.
        b = ResultBatch.objects.select_related("program", "session").filter(id=batch_id).first()
        if b:
            sem_start, sem_end, total_semesters = _semester_span_for(b.program_id, b.session_id)
            eligibility_map = transcript_eligibility_map(
                [result.enrollment for result in students]
            )

        # If only one student, auto-select
        if not enrollment_id and request.GET.get("action") != "print":
            only_enr = [r.enrollment_id for r in students][:2]
            if len(only_enr) == 1:
                enrollment_id = str(only_enr[0])

        # Reset stale selection
        if enrollment_id and enrollment_id.isdigit():
            selected_eligibility = eligibility_map.get(int(enrollment_id))
            if int(enrollment_id) not in [r.enrollment_id for r in students]:
                enrollment_id = ""
                selected_eligibility = None

    # Action: print
    if request.GET.get("action") == "print":
        if not batch_id:
            messages.error(request, "Please select a last-semester Result Batch.")
        elif not enrollment_id:
            messages.error(request, "Please select a Student.")
        elif not enrollment_id.isdigit():
            messages.error(request, "Please select a valid Student.")
        else:
            eligibility = eligibility_map.get(int(enrollment_id))
            if not eligibility or not eligibility.is_eligible:
                reason = (
                    eligibility.reason
                    if eligibility
                    else "Student is not part of the selected final-semester batch."
                )
                messages.error(request, f"Transcript is not available: {reason}")
            else:
                return redirect("transcript_pdf", enrollment_id=int(enrollment_id))

    return render(
        request,
        "dashboards/documents/transcript_single.html",
        {
            "departments": departments,
            "dept_id": str(dept_id) if dept_id else "",
            "programs": programs,
            "program_id": str(program_id) if program_id else "",
            "sessions": sessions,
            "session_id": str(session_id) if session_id else "",
            "max_sem": sem_end,
            "semester_start": sem_start,
            "semester_end": sem_end,
            "total_semesters": total_semesters,
            "batches": last_sem_batches,
            "batch_id": str(batch_id) if batch_id else "",
            "students": students,
            "eligibility_map": eligibility_map,
            "enrollment_id": str(enrollment_id) if enrollment_id else "",
            "selected_eligibility": selected_eligibility,
        },
    )


@group_required("System Admin", "Document Generator", "Controller", "Dealing Assistant")
def transcript_selected(request, batch_id):
    """UI: choose multiple students from a final-semester batch, then print one combined PDF.

    The PDF generation is handled by results.transcript_batch_pdf using selected enrollment IDs.
    """

    batch = get_object_or_404(
        ResultBatch.objects.select_related("department", "program", "session", "exam_type", "curriculum"),
        id=batch_id,
    )

    # Keep department restrictions consistent with the dashboard.
    allowed_batches = restrict_department_queryset(ResultBatch.objects.all(), request.user, "department")
    if not allowed_batches.filter(id=batch.id).exists():
        messages.error(request, "You do not have permission to access that result batch.")
        return redirect("dashboard")

    sem_start, sem_end, total_semesters = _semester_span_for(batch.program_id, batch.session_id)
    if not total_semesters or int(batch.semester_number) != int(sem_end):
        messages.error(request, "Selected transcripts are available only for the final semester batch.")
        return redirect("admin_batch_detail", pk=batch.id)

    students_qs = (
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
    students = list(students_qs)

    eligibility_map = transcript_eligibility_map(
        [result.enrollment for result in students]
    )
    if request.method == "POST":
        selected_ids = request.POST.getlist("enrollment_ids")
        selected_ids = [x for x in selected_ids if x.isdigit()]

        if not selected_ids:
            messages.error(request, "Please select at least one student.")
        else:
            student_ids = {str(result.enrollment_id) for result in students}
            invalid_batch_ids = [
                value for value in selected_ids if value not in student_ids
            ]
            ineligible_ids = [
                value
                for value in selected_ids
                if value in student_ids
                and not eligibility_map[int(value)].is_eligible
            ]

            if invalid_batch_ids:
                messages.error(
                    request,
                    "One or more selected students do not belong to this final-semester batch.",
                )
            elif ineligible_ids:
                first_status = eligibility_map[int(ineligible_ids[0])]
                messages.error(
                    request,
                    f"One or more selected students are not eligible: {first_status.reason}",
                )
            else:
                return redirect(
                    f"/results/transcript/batch/{batch.id}/pdf/"
                    f"?enrollments={','.join(selected_ids)}"
                )

    return render(
        request,
        "dashboards/documents/transcript_selected.html",
        {
            "batch": batch,
            "students": students,
            "eligibility_map": eligibility_map,
        },
    )
