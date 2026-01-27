from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError

from academics.models import ProgramCourse, Program
from dashboards.decorators import group_required
from dashboards.forms import ProgramCourseForm


@group_required("System Admin")
def program_course_list(request):
    qs = ProgramCourse.objects.select_related("department", "program", "course").all().order_by(
        "program__name", "semester_number", "course__code"
    )

    program_id = (request.GET.get("program") or "").strip()
    if program_id:
        qs = qs.filter(program_id=program_id)

    programs = Program.objects.all().order_by("name")

    return render(
        request,
        "dashboards/program_courses/list.html",
        {"items": qs, "program_id": program_id, "programs": programs},
    )

    # Optional filters
    program_id = request.GET.get("program")
    semester_no = request.GET.get("semester")

    if program_id:
        qs = qs.filter(program_id=program_id)
    if semester_no:
        qs = qs.filter(semester_number=semester_no)

    return render(
        request,
        "dashboards/program_courses/list.html",
        {"items": qs, "program_id": program_id, "semester_no": semester_no},
    )


@group_required("System Admin")
def program_course_create(request):
    if request.method == "POST":
        form = ProgramCourseForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Program course mapping created.")
                return redirect("admin_program_course_list")
            except IntegrityError:
                messages.error(request, "This mapping already exists.")
    else:
        form = ProgramCourseForm()

    return render(
        request,
        "dashboards/program_courses/form.html",
        {"form": form, "title": "Add Program Course"},
    )


@group_required("System Admin")
def program_course_update(request, pk):
    item = get_object_or_404(ProgramCourse, pk=pk)

    if request.method == "POST":
        form = ProgramCourseForm(request.POST, instance=item)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Program course mapping updated.")
                return redirect("admin_program_course_list")
            except IntegrityError:
                messages.error(request, "This mapping already exists.")
    else:
        form = ProgramCourseForm(instance=item)

    return render(
        request,
        "dashboards/program_courses/form.html",
        {"form": form, "title": "Edit Program Course", "item": item},
    )


@group_required("System Admin")
def program_course_delete(request, pk):
    item = get_object_or_404(ProgramCourse, pk=pk)

    if request.method == "POST":
        item.delete()
        messages.success(request, "Mapping deleted.")
        return redirect("admin_program_course_list")

    return render(
        request,
        "dashboards/program_courses/confirm_delete.html",
        {"item": item},
    )
