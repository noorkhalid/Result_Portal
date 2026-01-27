from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError

from students.models import Enrollment
from academics.models import Program, Session
from django.db.models import Q
from dashboards.decorators import group_required
from dashboards.forms import EnrollmentForm


@group_required("System Admin")
def enrollment_list(request):
    q = (request.GET.get("q") or "").strip()
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

    if q:
        enrollments = enrollments.filter(
            Q(roll_no__icontains=q)
            | Q(student__registration_no__icontains=q)
            | Q(student__name__icontains=q)
        )

    programs = Program.objects.all().order_by("name")
    sessions = Session.objects.all().order_by("-start_year")

    return render(
        request,
        "dashboards/enrollments/list.html",
        {
            "enrollments": enrollments,
            "q": q,
            "programs": programs,
            "sessions": sessions,
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
