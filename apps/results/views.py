from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.db.models import IntegerField
from django.db.models.functions import Cast, Substr
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string

from weasyprint import HTML

from academics.models import ProgramCourse
from .models import ResultBatch, SemesterResult, CourseResult


@login_required
def result_notification_pdf(request, batch_id):
    batch = get_object_or_404(ResultBatch, id=batch_id)

    # -------------------------------------------------
    # 1) Find which courses actually appear in THIS batch
    #    (so we don't show blank subject columns)
    # -------------------------------------------------
    batch_course_ids = list(
        CourseResult.objects.filter(batch=batch)
        .values_list("course_id", flat=True)
        .distinct()
    )

    # -------------------------------------------------
    # 2) Build columns (subjects) but ONLY keep those in batch_course_ids
    # -------------------------------------------------
    columns = []

    program_courses = (
        ProgramCourse.objects.filter(
            program=batch.program,
            semester_number=batch.semester_number,
            course_id__in=batch_course_ids,
        )
        .select_related("course")
        .order_by("id")
    )

    if program_courses.exists():
        for pc in program_courses:
            course = pc.course

            # credit hours (prefer course.credit_hours; fallback other fields)
            ch = getattr(course, "credit_hours", "")
            if ch in ("", None):
                th = getattr(course, "theory_credit", None)
                pr = getattr(course, "practical_credit", None)
                if th is not None or pr is not None:
                    th = th or 0
                    pr = pr or 0
                    ch = f"{th} ({pr})" if pr else f"{th}"
                else:
                    ch = getattr(pc, "credit_hours", "")

            columns.append(
                {
                    "course_id": pc.course_id,
                    "title": getattr(course, "title", str(course)),
                    "credit_hours": ch,
                }
            )
    else:
        # Fallback: build columns from CourseResult itself (still only this batch)
        distinct_courses = (
            CourseResult.objects.filter(batch=batch)
            .select_related("course")
            .order_by("course__title")
        )

        seen = set()
        for cr in distinct_courses:
            if cr.course_id in seen:
                continue
            seen.add(cr.course_id)

            course = cr.course
            ch = getattr(course, "credit_hours", "")
            if ch in ("", None):
                th = getattr(course, "theory_credit", None)
                pr = getattr(course, "practical_credit", None)
                if th is not None or pr is not None:
                    th = th or 0
                    pr = pr or 0
                    ch = f"{th} ({pr})" if pr else f"{th}"

            columns.append(
                {
                    "course_id": cr.course_id,
                    "title": getattr(course, "title", str(course)),
                    "credit_hours": ch,
                }
            )

    # -------------------------------------------------
    # 3) Student rows (one per enrollment)
    #    Fix sorting: BD1524-1, BD1524-2, ... BD1524-10
    # -------------------------------------------------
    # NOTE: This assumes roll_no format like "BD1524-10".
    # The suffix starts at character 8 (1-based) => "BD1524-" is 7 chars.
    results = (
        SemesterResult.objects.filter(batch=batch)
        .select_related("enrollment", "enrollment__student")
        .annotate(
            roll_suffix=Cast(
                Substr("enrollment__roll_no", 8),
                IntegerField(),
            )
        )
        .order_by("roll_suffix", "enrollment__roll_no")
    )

    # -------------------------------------------------
    # 4) grades_map[enrollment_id][course_id] = letter_grade
    # -------------------------------------------------
    grades_map = defaultdict(dict)
    cr_qs = (
        CourseResult.objects.filter(batch=batch)
        .select_related("enrollment", "course")
    )
    for cr in cr_qs:
        grades_map[cr.enrollment_id][cr.course_id] = (cr.letter_grade or "")

    session_display = batch.session.display_for_program(batch.program)

    # -------------------------------------------------
    # 5) Hide CGPA when semester is 1
    # -------------------------------------------------
    try:
        sem_no = int(batch.semester_number)
    except Exception:
        sem_no = 0

    show_cgpa = (sem_no != 1)

    # -------------------------------------------------
    # 6) Result type label for header
    #    UI wants: Regular OR Reappeared/Improved
    # -------------------------------------------------
    result_type_label = "Regular" if batch.result_type == "regular" else "Reappeared/Improved"

    html = render_to_string(
        "results/result_notification.html",
        {
            "batch": batch,
            "results": results,
            "columns": columns,
            "grades_map": grades_map,
            "session_display": session_display,
            "show_cgpa": show_cgpa,
            "result_type_label": result_type_label,
        },
        request=request,
    )

    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="Result_Notification_{batch.id}.pdf"'
    )
    return response
