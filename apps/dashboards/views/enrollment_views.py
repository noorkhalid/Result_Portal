from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError

from students.models import Enrollment
from academics.models import Department, Program, Session
from django.db.models import Q
from dashboards.decorators import group_required
from dashboards.forms import EnrollmentForm


@group_required("System Admin")
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

    if program_id:
        enrollments = enrollments.filter(program_id=program_id)
    if session_id:
        enrollments = enrollments.filter(session_id=session_id)
    if department_id:
        enrollments = enrollments.filter(department_id=department_id)

    if q:
        enrollments = enrollments.filter(
            Q(roll_no__icontains=q)
            | Q(student__registration_no__icontains=q)
            | Q(student__name__icontains=q)
        )

    departments = Department.objects.all().order_by("name")
    programs = Program.objects.all().order_by("name")
    if department_id:
        programs = programs.filter(department_id=department_id)

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


@group_required("System Admin")
def enrollment_create(request):
    if request.method == "POST":
        form = EnrollmentForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Enrollment created successfully.")
                return redirect("admin_enrollment_list")
            except IntegrityError:
                messages.error(request, "Roll number must be unique per program+session.")
    else:
        form = EnrollmentForm()

    return render(
        request,
        "dashboards/enrollments/form.html",
        {"form": form, "title": "Add Enrollment"},
    )


@group_required("System Admin")
def enrollment_update(request, pk):
    enrollment = get_object_or_404(Enrollment, pk=pk)

    if request.method == "POST":
        form = EnrollmentForm(request.POST, instance=enrollment)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Enrollment updated successfully.")
                return redirect("admin_enrollment_list")
            except IntegrityError:
                messages.error(request, "Roll number must be unique per program+session.")
    else:
        form = EnrollmentForm(instance=enrollment)

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
