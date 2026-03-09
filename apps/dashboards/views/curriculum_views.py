from collections import defaultdict

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from academics.models import (
    Curriculum,
    CurriculumCourse,
    Course,
    Program,
    Session,
)
from dashboards.decorators import group_required


def _previous_session_for(program: Program, session: Session) -> Session | None:
    """Return the most recent Session before the given one (by start_year)."""
    return (
        Session.objects.filter(start_year__lt=session.start_year)
        .order_by("-start_year")
        .first()
    )


@group_required("System Admin")
def curriculum_designer(request):
    """Curriculum Designer (by Program + Session).

    - Select Program + Session via query string
    - Shows semester blocks based on Curriculum.total_semesters
    - Lets you add/remove CurriculumCourse rows
    - Includes a safe "Copy from previous session" action
    """

    programs = Program.objects.all().order_by("name")
    sessions = Session.objects.all().order_by("-start_year")
    courses = Course.objects.all().order_by("code")

    program_id = (request.GET.get("program") or "").strip()
    session_id = (request.GET.get("session") or "").strip()

    selected_program = None
    selected_session = None
    curriculum = None
    semesters: dict[int, list[CurriculumCourse]] = {}
    available_courses: dict[int, list[Course]] = {}

    if program_id and session_id:
        selected_program = get_object_or_404(Program, pk=program_id)
        selected_session = get_object_or_404(Session, pk=session_id)

        curriculum, _ = Curriculum.objects.get_or_create(
            program=selected_program,
            session=selected_session,
            defaults={
                "total_semesters": selected_program.total_semesters,
                "semester_start": getattr(selected_program, "semester_start", 1) or 1,
            },
        )

        total = int(curriculum.total_semesters or 0)
        sem_start = int(getattr(curriculum, "semester_start", 1) or 1)
        sem_end = int(getattr(curriculum, "semester_end", 0) or 0)

        qs = (
            CurriculumCourse.objects.filter(curriculum=curriculum)
            .select_related("course")
            .order_by("semester_number", "course__code")
        )

        grouped = defaultdict(list)
        for cc in qs:
            grouped[int(cc.semester_number)].append(cc)

        for sem in range(sem_start, (sem_end or sem_start - 1) + 1):
            semesters[sem] = grouped.get(sem, [])

        # Courses available per semester (hide already-added courses from the dropdown)
        for sem in range(sem_start, (sem_end or sem_start - 1) + 1):
            existing_ids = [cc.course_id for cc in semesters.get(sem, [])]
            available_courses[sem] = list(courses.exclude(id__in=existing_ids))

    prev_session = None
    if selected_program and selected_session:
        prev_session = _previous_session_for(selected_program, selected_session)

    return render(
        request,
        "dashboards/curricula/designer.html",
        {
            "programs": programs,
            "sessions": sessions,
            "courses": courses,
            "program_id": program_id,
            "session_id": session_id,
            "selected_program": selected_program,
            "selected_session": selected_session,
            "curriculum": curriculum,
            "semesters": semesters,
            "available_courses": available_courses,
            "prev_session": prev_session,
        },
    )


@group_required("System Admin")
def curriculum_course_add(request):
    if request.method != "POST":
        messages.info(request, "Use Curriculum Designer to add courses.")
        return redirect("admin_curriculum_designer")

    curriculum_id = (request.POST.get("curriculum") or "").strip()
    semester_number = (request.POST.get("semester_number") or "").strip()
    # Multi-select support: can submit multiple course IDs.
    course_ids = request.POST.getlist("course_ids")
    if not course_ids:
        # Backward compatible (older template)
        one = (request.POST.get("course") or "").strip()
        if one:
            course_ids = [one]

    if not (curriculum_id and semester_number and course_ids):
        messages.error(request, "Missing curriculum, semester, or course.")
        return redirect("admin_curriculum_designer")

    curriculum = get_object_or_404(Curriculum, pk=curriculum_id)

    try:
        sem_int = int(semester_number)
    except ValueError:
        messages.error(request, "Invalid semester number.")
        return redirect(
            f"{reverse('admin_curriculum_designer')}?program={curriculum.program_id}&session={curriculum.session_id}"
        )

    total = int(curriculum.total_semesters or 0)
    sem_start = int(getattr(curriculum, "semester_start", 1) or 1)
    sem_end = int(getattr(curriculum, "semester_end", 0) or 0)
    if sem_int < sem_start or sem_int > sem_end:
        messages.error(request, "Semester number is out of range for this curriculum.")
        return redirect(
            f"{reverse('admin_curriculum_designer')}?program={curriculum.program_id}&session={curriculum.session_id}"
        )

    added = 0
    for cid in course_ids:
        obj, created = CurriculumCourse.objects.get_or_create(
            curriculum=curriculum,
            semester_number=sem_int,
            course_id=cid,
        )
        if created:
            added += 1

    if added:
        messages.success(request, f"Added {added} course(s).")
    else:
        messages.info(request, "No new courses were added (already present).")

    return redirect(
        f"{reverse('admin_curriculum_designer')}?program={curriculum.program_id}&session={curriculum.session_id}"
    )


@group_required("System Admin")
def curriculum_course_delete(request, pk):
    item = get_object_or_404(CurriculumCourse, pk=pk)
    curriculum = item.curriculum

    if request.method == "POST":
        item.delete()
        messages.success(request, "Course removed.")
    else:
        messages.info(request, "Please use the Remove button.")

    return redirect(
        f"{reverse('admin_curriculum_designer')}?program={curriculum.program_id}&session={curriculum.session_id}"
    )


@group_required("System Admin")
def curriculum_copy_previous(request):
    """Copy CurriculumCourse rows from the previous session into the selected curriculum.

    Safety behavior:
    - If the target curriculum already has any courses, we do NOT overwrite.
    - Source is previous session's curriculum for the same program.
    - Requires previous session's curriculum to exist.
    """

    if request.method != "POST":
        messages.info(request, "Use the button in Curriculum Designer.")
        return redirect("admin_curriculum_designer")

    program_id = (request.POST.get("program") or "").strip()
    session_id = (request.POST.get("session") or "").strip()

    if not (program_id and session_id):
        messages.error(request, "Missing program or session.")
        return redirect("admin_curriculum_designer")

    program = get_object_or_404(Program, pk=program_id)
    session = get_object_or_404(Session, pk=session_id)

    curriculum, _ = Curriculum.objects.get_or_create(
        program=program,
        session=session,
        defaults={
            "total_semesters": program.total_semesters,
            "semester_start": getattr(program, "semester_start", 1) or 1,
        },
    )

    if CurriculumCourse.objects.filter(curriculum=curriculum).exists():
        messages.warning(
            request,
            "This curriculum already has courses. For safety, copy is blocked to avoid overwriting.",
        )
        return redirect(f"{reverse('admin_curriculum_designer')}?program={program_id}&session={session_id}")

    prev = _previous_session_for(program, session)
    copied = 0

    with transaction.atomic():
        # 1) Preferred source: previous session curriculum
        if prev:
            prev_cur = Curriculum.objects.filter(program=program, session=prev).first()
            if prev_cur:
                src_rows = list(
                    CurriculumCourse.objects.filter(curriculum=prev_cur)
                    .values("semester_number", "course_id", "credit_hours_override")
                )
                for row in src_rows:
                    CurriculumCourse.objects.get_or_create(
                        curriculum=curriculum,
                        semester_number=row["semester_number"],
                        course_id=row["course_id"],
                        defaults={"credit_hours_override": row["credit_hours_override"]},
                    )
                copied = len(src_rows)

        # No other fallback is allowed in v4.

    if copied:
        messages.success(request, f"Copied {copied} course mappings into this session's curriculum.")
    else:
        messages.error(
            request,
            "Nothing to copy. Create the previous session curriculum first.",
        )

    return redirect(f"{reverse('admin_curriculum_designer')}?program={program_id}&session={session_id}")
