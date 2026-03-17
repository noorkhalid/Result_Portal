from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError

from students.models import Enrollment
from academics.models import Department, Program, Session
from django.db.models import Q
from dashboards.decorators import group_required
from dashboards.forms import EnrollmentForm
from dashboards.access import assigned_departments_qs, is_dealing_assistant

from results.models import ResultBatch, SemesterResult, CourseResult



@group_required("System Admin", "Dealing Assistant")
def enrollment_list(request):
    q = (request.GET.get("q") or "").strip()
    department_id = (request.GET.get("department") or "").strip()
    program_id = (request.GET.get("program") or "").strip()
    session_id = (request.GET.get("session") or "").strip()

    enrollments = (
        Enrollment.objects.select_related("student", "program", "session")
        .all()
        .order_by("-session__start_year", "program__name", "roll_no")
    )
    departments = assigned_departments_qs(request.user) if is_dealing_assistant(request.user) and not (request.user.is_superuser or request.user.groups.filter(name="System Admin").exists()) else Department.objects.all().order_by("name")

    if program_id:
        enrollments = enrollments.filter(program_id=program_id)
    if session_id:
        enrollments = enrollments.filter(session_id=session_id)
    if department_id:
        enrollments = enrollments.filter(department_id=department_id)
    elif is_dealing_assistant(request.user) and not (request.user.is_superuser or request.user.groups.filter(name="System Admin").exists()):
        enrollments = enrollments.filter(department__assigned_assistant=request.user)

    if q:
        enrollments = enrollments.filter(
            Q(roll_no__icontains=q)
            | Q(student__registration_no__icontains=q)
            | Q(student__name__icontains=q)
        )

    programs = Program.objects.all().order_by("name")
    if department_id:
        programs = programs.filter(offerings__department_id=department_id, offerings__is_active=True).distinct()
    elif is_dealing_assistant(request.user) and not (request.user.is_superuser or request.user.groups.filter(name="System Admin").exists()):
        programs = programs.filter(offerings__department__assigned_assistant=request.user, offerings__is_active=True).distinct()

    # If selected program is not valid for this department, reset dependent filters
    invalid_program = False
    if program_id and not programs.filter(id=program_id).exists():
        invalid_program = True
        program_id = ""
        session_id = ""

    # If we reset an invalid program, rebuild the enrollments queryset without that filter
    if invalid_program:
        enrollments = (
            Enrollment.objects.select_related("student", "program", "session")
            .all()
            .order_by("-session__start_year", "program__name", "roll_no")
        )
        if is_dealing_assistant(request.user) and not (request.user.is_superuser or request.user.groups.filter(name="System Admin").exists()):
            enrollments = enrollments.filter(department__assigned_assistant=request.user)
        if department_id:
            enrollments = enrollments.filter(department_id=department_id)
        if q:
            enrollments = enrollments.filter(
                Q(roll_no__icontains=q)
                | Q(student__registration_no__icontains=q)
                | Q(student__name__icontains=q)
            )

    # Sessions depend on selected dept/program (via existing enrollments)
    base_for_sessions = Enrollment.objects.all()
    if is_dealing_assistant(request.user) and not (request.user.is_superuser or request.user.groups.filter(name="System Admin").exists()):
        base_for_sessions = base_for_sessions.filter(department__assigned_assistant=request.user)
    if department_id:
        base_for_sessions = base_for_sessions.filter(department_id=department_id)
    if program_id:
        base_for_sessions = base_for_sessions.filter(program_id=program_id)
    sessions = Session.objects.filter(
        id__in=base_for_sessions.values_list("session_id", flat=True).distinct()
    ).order_by("-start_year")

    # If selected session is not valid for this department/program, reset it
    if session_id and not sessions.filter(id=session_id).exists():
        session_id = ""

    return render(
        request,
        "dashboards/enrollments/list.html",
        {
            "enrollments": enrollments,
            "q": q,
            "departments": departments,
            "programs": programs,
            "sessions": sessions,
            "department_id": department_id,
            "program_id": program_id,
            "session_id": session_id,
        },
    )


@group_required("System Admin", "Dealing Assistant")
def enrollment_create(request):
    if request.method == "POST":
        form = EnrollmentForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Enrollment created successfully.")
                return redirect("admin_enrollment_list")
            except IntegrityError:
                messages.error(request, "Roll number must be unique per program+session.")
    else:
        form = EnrollmentForm(user=request.user)

    return render(
        request,
        "dashboards/enrollments/form.html",
        {"form": form, "title": "Add Enrollment"},
    )


@group_required("System Admin", "Dealing Assistant")
def enrollment_update(request, pk):
    qs = Enrollment.objects.all()
    if is_dealing_assistant(request.user) and not (request.user.is_superuser or request.user.groups.filter(name="System Admin").exists()):
        qs = qs.filter(department__assigned_assistant=request.user)
    enrollment = get_object_or_404(qs, pk=pk)

    if request.method == "POST":
        form = EnrollmentForm(request.POST, instance=enrollment, user=request.user)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Enrollment updated successfully.")
                return redirect("admin_enrollment_list")
            except IntegrityError:
                messages.error(request, "Roll number must be unique per program+session.")
    else:
        form = EnrollmentForm(instance=enrollment, user=request.user)

    return render(
        request,
        "dashboards/enrollments/form.html",
        {"form": form, "title": "Edit Enrollment", "enrollment": enrollment},
    )


@group_required("System Admin")
def enrollment_delete(request, pk):
    enrollment = get_object_or_404(Enrollment, pk=pk)

    delete_blocked = enrollment.course_results.exists() or enrollment.semester_results.exists()

    if request.method == "POST":
        if delete_blocked:
            messages.error(request, "Cannot delete: results exist for this enrollment.")
            return redirect("admin_enrollment_list")

        enrollment.delete()
        messages.success(request, "Enrollment deleted successfully.")
        return redirect("admin_enrollment_list")

    return render(
        request,
        "dashboards/enrollments/confirm_delete.html",
        {"enrollment": enrollment, "delete_blocked": delete_blocked},
    )


@group_required("System Admin", "Dealing Assistant")
def enrollment_detail(request, pk):
    """Single student's academic record (results across semesters).

    We intentionally anchor this page on Enrollment (Program+Session),
    not Student, because results are always tied to an enrollment.
    """

    enrollment_qs = Enrollment.objects.select_related(
            "student", "department", "program", "session", "curriculum"
        )
    if is_dealing_assistant(request.user) and not (request.user.is_superuser or request.user.groups.filter(name="System Admin").exists()):
        enrollment_qs = enrollment_qs.filter(department__assigned_assistant=request.user)
    enrollment = get_object_or_404(enrollment_qs, pk=pk)

    # Semester span comes from curriculum snapshot first (stable), then program.
    total_semesters = int(getattr(enrollment.curriculum, "total_semesters", 0) or 0)
    sem_start = int(getattr(enrollment.curriculum, "semester_start", 0) or 0)
    sem_end = int(getattr(enrollment.curriculum, "semester_end", 0) or 0)

    if total_semesters <= 0:
        total_semesters = int(getattr(enrollment.program, "total_semesters", 0) or 0)
    if sem_start <= 0:
        sem_start = int(getattr(enrollment.program, "semester_start", 1) or 1)
    if sem_end <= 0:
        sem_end = int(getattr(enrollment.program, "semester_end", 0) or 0)

    batches = (
        ResultBatch.objects.filter(
            department_id=enrollment.department_id,
            program_id=enrollment.program_id,
            session_id=enrollment.session_id,
        )
        .select_related("exam_type")
        .order_by("semester_number", "exam_type__sort_order", "exam_type__name", "-created_at")
    )

    semester_results = {
        sr.batch_id: sr
        for sr in (
            SemesterResult.objects.filter(
                enrollment=enrollment, batch__in=batches
            )
            .select_related("batch", "batch__exam_type")
        )
    }

    course_results = {}
    for cr in (
        CourseResult.objects.filter(enrollment=enrollment, batch__in=batches)
        .select_related("batch", "batch__exam_type", "course")
        .order_by("course__code")
    ):
        course_results.setdefault(cr.batch_id, []).append(cr)

    # latest/first notification per batch (for "Declared" badges)
    notifications_by_batch = {}
    for b in batches:
        n = b.notifications.order_by("created_at").first()
        notifications_by_batch[b.id] = n

    # Group by semester_number for UI
    semesters = []
    if total_semesters and sem_end:
        sem_numbers = list(range(sem_start, sem_end + 1))
    else:
        sem_numbers = sorted(set(batches.values_list("semester_number", flat=True)))

    for sem_no in sem_numbers:
        sem_batches = [b for b in batches if int(b.semester_number) == int(sem_no)]
        semesters.append(
            {
                "number": sem_no,
                "batches": [
                    {
                        "batch": b,
                        "semester_result": semester_results.get(b.id),
                        "course_results": course_results.get(b.id, []),
                        "notification": notifications_by_batch.get(b.id),
                    }
                    for b in sem_batches
                ],
            }
        )

    return render(
        request,
        "dashboards/enrollments/detail.html",
        {
            "enrollment": enrollment,
            "total_semesters": total_semesters,
            "semester_start": sem_start,
            "semester_end": sem_end,
            "semesters": semesters,
        },
    )


@group_required("System Admin")
def enrollment_delete_marks_from_batch(request, enrollment_id, batch_id):
    """Delete one student's marks from one batch (safe-guarded)."""

    enrollment = get_object_or_404(
        Enrollment.objects.select_related("student", "program", "session", "department"),
        pk=enrollment_id,
    )
    batch = get_object_or_404(
        ResultBatch.objects.select_related("program", "session", "department", "exam_type"),
        pk=batch_id,
    )

    # Safety: must match enrollment scope
    if (
        batch.department_id != enrollment.department_id
        or batch.program_id != enrollment.program_id
        or batch.session_id != enrollment.session_id
    ):
        messages.error(request, "This batch does not belong to the selected enrollment.")
        return redirect("admin_enrollment_detail", pk=enrollment.pk)

    sr = SemesterResult.objects.filter(batch=batch, enrollment=enrollment).first()
    delete_blocked = bool(sr and sr.notification_items.exists())

    if request.method == "POST":
        if delete_blocked:
            messages.error(request, "Cannot delete: this student's result is already included in a notification.")
            return redirect("admin_enrollment_detail", pk=enrollment.pk)

        CourseResult.objects.filter(batch=batch, enrollment=enrollment).delete()
        SemesterResult.objects.filter(batch=batch, enrollment=enrollment).delete()
        messages.success(request, "Student marks deleted from the selected batch.")
        return redirect("admin_enrollment_detail", pk=enrollment.pk)

    return render(
        request,
        "dashboards/enrollments/confirm_delete_marks.html",
        {
            "enrollment": enrollment,
            "batch": batch,
            "delete_blocked": delete_blocked,
        },
    )
