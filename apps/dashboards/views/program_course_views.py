from collections import defaultdict

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError
from django.urls import reverse

from academics.models import ProgramCourse, Program, Course
from dashboards.decorators import group_required


@group_required("System Admin")
def program_course_list(request):
    """
    Curriculum Designer (replaces the old ProgramCourse table view).

    - Program is selected via ?program=<id>
    - Renders semester blocks 1..program.total_semesters
    - Add/remove course mappings from within the designer
    """
    programs = Program.objects.all().order_by("name")
    courses = Course.objects.all().order_by("code")

    program_id = (request.GET.get("program") or "").strip()
    selected_program = None
    semesters = {}

    if program_id:
        selected_program = get_object_or_404(Program, pk=program_id)
        total = selected_program.total_semesters or 0

        qs = (
            ProgramCourse.objects
            .filter(program=selected_program)
            .select_related("course")
            .order_by("semester_number", "course__code")
        )

        grouped = defaultdict(list)
        for pc in qs:
            grouped[int(pc.semester_number)].append(pc)

        for sem in range(1, total + 1):
            semesters[sem] = grouped.get(sem, [])

    return render(
        request,
        "dashboards/program_courses/list.html",
        {
            "programs": programs,
            "courses": courses,
            "program_id": program_id,
            "selected_program": selected_program,
            "semesters": semesters,
        },
    )


@group_required("System Admin")
def program_course_create(request):
    """Add a course to a semester (used by Curriculum Designer)."""
    if request.method != "POST":
        messages.info(request, "Use the Curriculum Designer to add courses.")
        return redirect("admin_program_course_list")

    program_id = (request.POST.get("program") or "").strip()
    semester_number = (request.POST.get("semester_number") or "").strip()
    course_id = (request.POST.get("course") or "").strip()

    if not (program_id and semester_number and course_id):
        messages.error(request, "Missing program, semester or course.")
        return redirect("admin_program_course_list")

    # Validate program + semester range
    program = get_object_or_404(Program, pk=program_id)
    try:
        sem_int = int(semester_number)
    except ValueError:
        messages.error(request, "Invalid semester number.")
        return redirect(f"{reverse('admin_program_course_list')}?program={program_id}")

    if sem_int < 1 or sem_int > (program.total_semesters or 0):
        messages.error(request, "Semester number is out of range for the selected program.")
        return redirect(f"{reverse('admin_program_course_list')}?program={program_id}")

    # Create mapping (ignore duplicates)
    try:
        ProgramCourse.objects.get_or_create(
            program_id=program_id,
            semester_number=sem_int,
            course_id=course_id,
        )
        messages.success(request, "Course added to semester.")
    except IntegrityError:
        # In case the DB has a unique constraint and races
        messages.warning(request, "This course is already added in that semester.")

    return redirect(f"{reverse('admin_program_course_list')}?program={program_id}")


@group_required("System Admin")
def program_course_update(request, pk):
    """Editing is intentionally disabled in the new designer flow."""
    messages.info(request, "Editing is disabled. Remove the course and add it again in the desired semester.")
    return redirect("admin_program_course_list")


@group_required("System Admin")
def program_course_delete(request, pk):
    """Remove a course mapping (used by Curriculum Designer)."""
    item = get_object_or_404(ProgramCourse, pk=pk)
    program_id = item.program_id

    if request.method == "POST":
        item.delete()
        messages.success(request, "Course removed from semester.")
    else:
        messages.info(request, "Please use the Remove button in Curriculum Designer.")

    return redirect(f"{reverse('admin_program_course_list')}?program={program_id}")
