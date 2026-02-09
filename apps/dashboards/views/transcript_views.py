from __future__ import annotations

from django.contrib import messages
from django.db.models import Count, F
from django.shortcuts import redirect, render

from dashboards.decorators import group_required
from academics.models import Department, Program, Session, Curriculum
from results.models import ResultBatch, SemesterResult


def _max_semester_for(program_id: str | int, session_id: str | int) -> int:
    """Return the authoritative max semester for a program+session.

    IMPORTANT:
    We no longer rely on the Semester table for max-semester logic because it
    duplicates Program.total_semesters and can go out-of-sync. Session is kept
    in the signature for backward-compatibility with the UI flow.
    """
    cur = Curriculum.objects.filter(program_id=program_id, session_id=session_id).only("total_semesters").first()
    if cur:
        return int(cur.total_semesters)
    cur = (
        Curriculum.objects.filter(program_id=program_id, session_id=session_id)
        .only("total_semesters")
        .first()
    )
    if cur:
        return int(cur.total_semesters)
    program = Program.objects.filter(id=program_id).only("total_semesters").first()
    return int(program.total_semesters) if program else 0


@group_required("System Admin", "Document Generator", "Controller")
def transcript_single(request):
    """UI: pick Department → Program → Session → (auto last semester batch) → Student, then print Transcript.

    Rule:
      Transcript is only available when the student has results for ALL semesters
      defined in all semesters (1..Program.total_semesters) for that program+session.

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

    departments = Department.objects.all().order_by("name")

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

    max_sem = 0
    last_sem_batches = ResultBatch.objects.none()
    if program_id and session_id:
        max_sem = _max_semester_for(program_id, session_id)
        if max_sem:
            last_sem_batches = batches_qs.filter(semester_number=max_sem)

    # If stale session selection, reset
    if session_id and not sessions.filter(id=session_id).exists():
        session_id = ""
        batch_id = ""
        enrollment_id = ""
        max_sem = 0
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
    completed_map = {}
    selected_completed = None

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

        # Completion check in bulk (count distinct semester numbers for each enrollment)
        b = ResultBatch.objects.select_related("program", "session").filter(id=batch_id).first()
        if b:
            max_sem = _max_semester_for(b.program_id, b.session_id)
            enrollment_ids = [r.enrollment_id for r in students]
            counts = (
                SemesterResult.objects.filter(
                    enrollment_id__in=enrollment_ids,
                    batch__program_id=b.program_id,
                    batch__session_id=b.session_id,
                    batch__semester_number__lte=max_sem,
                )
                .values("enrollment_id")
                .annotate(sem_count=Count("batch__semester_number", distinct=True))
            )
            completed_map = {row["enrollment_id"]: (row["sem_count"] >= max_sem and max_sem > 0) for row in counts}

        # If only one student, auto-select
        if not enrollment_id and request.GET.get("action") != "print":
            only_enr = [r.enrollment_id for r in students][:2]
            if len(only_enr) == 1:
                enrollment_id = str(only_enr[0])

        # Reset stale selection
        if enrollment_id and enrollment_id.isdigit():
            selected_completed = completed_map.get(int(enrollment_id))
            if int(enrollment_id) not in [r.enrollment_id for r in students]:
                enrollment_id = ""
                selected_completed = None

    # Action: print
    if request.GET.get("action") == "print":
        if not batch_id:
            messages.error(request, "Please select a last-semester Result Batch.")
        elif not enrollment_id:
            messages.error(request, "Please select a Student.")
        elif enrollment_id.isdigit() and not completed_map.get(int(enrollment_id), False):
            messages.error(request, "Transcript is not available: student has not completed all semester results yet.")
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
            "max_sem": max_sem,
            "batches": last_sem_batches,
            "batch_id": str(batch_id) if batch_id else "",
            "students": students,
            "completed_map": completed_map,
            "enrollment_id": str(enrollment_id) if enrollment_id else "",
            "selected_completed": selected_completed,
        },
    )
