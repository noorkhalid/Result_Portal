from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError

from academics.models import Semester, Program, Session
from dashboards.decorators import group_required
from dashboards.forms import SemesterForm


@group_required("System Admin")
def semester_list(request):
    semesters = Semester.objects.select_related("program", "session").all().order_by(
        "-session__start_year", "program__name", "number"
    )

    program_id = (request.GET.get("program") or "").strip()
    session_id = (request.GET.get("session") or "").strip()

    if program_id:
        semesters = semesters.filter(program_id=program_id)
    if session_id:
        semesters = semesters.filter(session_id=session_id)

    programs = Program.objects.all().order_by("name")
    sessions = Session.objects.all().order_by("-start_year")

    return render(
        request,
        "dashboards/semesters/list.html",
        {
            "semesters": semesters,
            "programs": programs,
            "sessions": sessions,
            "program_id": program_id,
            "session_id": session_id,
        },
    )


@group_required("System Admin")
def semester_create(request):
    if request.method == "POST":
        form = SemesterForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Semester created successfully.")
                return redirect("admin_semester_list")
            except IntegrityError:
                messages.error(request, "This semester already exists for that program/session.")
    else:
        form = SemesterForm()

    return render(
        request,
        "dashboards/semesters/form.html",
        {"form": form, "title": "Add Semester"},
    )


@group_required("System Admin")
def semester_update(request, pk):
    semester = get_object_or_404(Semester, pk=pk)

    if request.method == "POST":
        form = SemesterForm(request.POST, instance=semester)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Semester updated successfully.")
                return redirect("admin_semester_list")
            except IntegrityError:
                messages.error(request, "This semester already exists for that program/session.")
    else:
        form = SemesterForm(instance=semester)

    return render(
        request,
        "dashboards/semesters/form.html",
        {"form": form, "title": "Edit Semester", "semester": semester},
    )


@group_required("System Admin")
def semester_delete(request, pk):
    semester = get_object_or_404(Semester, pk=pk)

    delete_blocked = False
    # if you later link results to Semester model, add checks here

    if request.method == "POST":
        if delete_blocked:
            messages.error(request, "Cannot delete: this semester is in use.")
            return redirect("admin_semester_list")

        semester.delete()
        messages.success(request, "Semester deleted successfully.")
        return redirect("admin_semester_list")

    return render(
        request,
        "dashboards/semesters/confirm_delete.html",
        {"semester": semester, "delete_blocked": delete_blocked},
    )
