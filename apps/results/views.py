from collections import defaultdict
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import IntegerField
from django.db.models.functions import Cast, Substr
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.db.models import Max
from django.db import models

from weasyprint import HTML

from academics.models import ProgramCourse, Semester
from students.models import Enrollment
from .models import ResultBatch, SemesterResult, CourseResult, GradeScale


def _course_columns_for_batch(batch: ResultBatch):
    """Return ordered ProgramCourse rows for the batch, limited to courses that exist in the batch."""
    batch_course_ids = list(
        CourseResult.objects.filter(batch=batch)
        .values_list("course_id", flat=True)
        .distinct()
    )

    return (
        ProgramCourse.objects.filter(
            program=batch.program,
            semester_number=batch.semester_number,
            course_id__in=batch_course_ids,
        )
        .select_related("course")
        .order_by("id")
    )


def _build_gpa_history(enrollment_id: int, batch: ResultBatch):
    """Return a list of (semester_number, gpa) up to the current semester.

    If there are multiple batches for a semester (repeat/improved), the latest one (by batch.created_at)
    is used.
    """
    try:
        current_sem = int(batch.semester_number)
    except Exception:
        current_sem = 0

    qs = (
        SemesterResult.objects.filter(
            enrollment_id=enrollment_id,
            batch__program=batch.program,
            batch__session=batch.session,
            batch__semester_number__lte=current_sem,
        )
        .select_related("batch")
        .order_by("batch__semester_number", "-batch__created_at")
    )

    picked = {}
    for sr in qs:
        sem = int(sr.batch.semester_number)
        if sem not in picked:
            picked[sem] = sr

    out = []
    for sem in sorted(picked.keys()):
        out.append((sem, picked[sem].gpa))
    return out


def _roll_suffix_annotation():
    """Annotation used for natural sorting of roll numbers like BD1524-10."""
    return Cast(Substr("enrollment__roll_no", 8), IntegerField())


def _max_semester_for_program_session(program_id: int, session_id: int) -> int:
    """Highest semester number according to the Semester table.

    In this project, the "last semester" is defined as the highest semester number
    configured for the Program in the Semester table (not per-session).

    We keep this helper for backward-compatibility, but intentionally fall back to
    program-only if program+session rows don't exist.
    """

    mx = (
        Semester.objects.filter(program_id=program_id, session_id=session_id)
        .aggregate(m=Max("number"))
        .get("m")
    )
    if not mx:
        mx = Semester.objects.filter(program_id=program_id).aggregate(m=Max("number")).get("m")
    return int(mx or 0)


def _is_program_completed(enrollment: Enrollment, max_semester: int) -> bool:
    if not max_semester:
        return False
    done = (
        SemesterResult.objects.filter(
            enrollment=enrollment,
            batch__program=enrollment.program,
            batch__session=enrollment.session,
            batch__semester_number__lte=max_semester,
        )
        .values_list("batch__semester_number", flat=True)
        .distinct()
    )
    return len(list(done)) >= int(max_semester)


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


@login_required
def dmc_single_pdf(request, batch_id, enrollment_id):
    """Generate a single-student DMC (one DMC per student per semester/batch)."""
    batch = get_object_or_404(ResultBatch, id=batch_id)
    sem_res = get_object_or_404(
        SemesterResult.objects.select_related("enrollment", "enrollment__student"),
        batch=batch,
        enrollment_id=enrollment_id,
    )

    columns = list(_course_columns_for_batch(batch))
    course_map = {
        cr.course_id: cr
        for cr in CourseResult.objects.filter(batch=batch, enrollment_id=enrollment_id)
        .select_related("course")
    }

    # DMC layout is optimized for a strict maximum of 10 subjects.
    course_rows = []
    for pc in columns:
        cr = course_map.get(pc.course_id)
        if not cr:
            continue
        ch = cr.course.credit_hours
        gp_total = (cr.grade_point or 0) * ch
        course_rows.append(
            {
                "title": cr.course.title,
                "credit_hours": ch,
                "marks_pct": cr.percentage,
                "grade": cr.letter_grade,
                "ng": cr.grade_point,
                "gp_total": gp_total,
            }
        )

    # Hard limit for print-fit: max 10 subjects per semester.
    course_rows = course_rows[:10]

    # NOTE: DMC footer must show ONLY current semester GPA, and CGPA label as "CGPA".
    # CGPA logic remains "up to this semester" (SemesterResult.cgpa).

    html = render_to_string(
        "results/dmc_batch.html",
        {
            "batch": batch,
            "session_display": batch.session.display_for_program(batch.program),
            "dmcs": [
                {
                    "enrollment": sem_res.enrollment,
                    "student": sem_res.enrollment.student,
                    "semester_result": sem_res,
                    "course_rows": course_rows,
                }
            ],
        },
        request=request,
    )

    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="DMC_{batch.id}_{enrollment_id}.pdf"'
    )
    return response


@login_required
def dmc_batch_pdf(request, batch_id):
    """Generate a multi-page PDF (one page per student) for a batch."""
    batch = get_object_or_404(ResultBatch, id=batch_id)

    # Courses/ordering for this semester
    columns = list(_course_columns_for_batch(batch))
    ordered_course_ids = [pc.course_id for pc in columns]

    # Natural sort of roll numbers
    results = (
        SemesterResult.objects.filter(batch=batch)
        .select_related("enrollment", "enrollment__student")
        .annotate(roll_suffix=_roll_suffix_annotation())
        .order_by("roll_suffix", "enrollment__roll_no")
    )

    # Pull all course results for batch in one go
    cr_qs = (
        CourseResult.objects.filter(batch=batch)
        .select_related("course")
        .order_by("id")
    )
    cr_map = defaultdict(dict)  # cr_map[enrollment_id][course_id] = CourseResult
    for cr in cr_qs:
        cr_map[cr.enrollment_id][cr.course_id] = cr

    dmcs = []
    for sr in results:
        enrollment_id = sr.enrollment_id
        course_rows = []

        for course_id in ordered_course_ids:
            cr = cr_map.get(enrollment_id, {}).get(course_id)
            if not cr:
                continue
            ch = cr.course.credit_hours
            gp_total = (cr.grade_point or 0) * ch
            course_rows.append(
                {
                    "title": cr.course.title,
                    "credit_hours": ch,
                    "marks_pct": cr.percentage,
                    "grade": cr.letter_grade,
                    "ng": cr.grade_point,
                    "gp_total": gp_total,
                }
            )

        # Hard limit for print-fit: max 10 subjects per semester.
        course_rows = course_rows[:10]
        dmcs.append(
            {
                "enrollment": sr.enrollment,
                "student": sr.enrollment.student,
                "semester_result": sr,
                "course_rows": course_rows,
            }
        )

    html = render_to_string(
        "results/dmc_batch.html",
        {
            "batch": batch,
            "session_display": batch.session.display_for_program(batch.program),
            "dmcs": dmcs,
        },
        request=request,
    )

    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="DMC_Batch_{batch.id}.pdf"'
    return response


def _program_max_semester(program_id: int) -> int:
    """Highest semester number defined in the Semester table for a program.

    IMPORTANT: In this project, "last semester" is defined as the highest semester
    number configured for the Program in the Semester table (not per-session).
    """

    return (
        Semester.objects.filter(program_id=program_id)
        .aggregate(m=Max("number"))
        .get("m")
        or 0
    )


def _enrollment_is_completed(enrollment: Enrollment, max_sem: int) -> bool:
    """Completed means: at least one SemesterResult exists for every semester 1..max_sem."""
    if max_sem <= 0:
        return False

    done = (
        SemesterResult.objects.filter(
            enrollment=enrollment,
            batch__program_id=enrollment.program_id,
            batch__session_id=enrollment.session_id,
            batch__semester_number__lte=max_sem,
        )
        .values_list("batch__semester_number", flat=True)
        .distinct()
    )
    return len(list(done)) >= max_sem


@login_required
def transcript_pdf(request, enrollment_id: int):
    """Generate a full transcript PDF for an enrollment (Program+Session).

    Rules:
      - Last semester is the highest semester number defined for the Program in academics.Semester.
      - Transcript is allowed only when the student has results for ALL semesters (1..last semester).
      - Layout:
          * <= 3 semesters  -> single column (stacked)
          * >  3 semesters  -> two columns (paired semesters)
      - Footer Letter Grade and Remarks are calculated from OVERALL percentage marks
        across ALL semesters (using GradeScale table).
    """

    enrollment = get_object_or_404(
        Enrollment.objects.select_related("student", "program", "session", "department"),
        id=enrollment_id,
    )

    max_sem = _program_max_semester(enrollment.program_id)
    if max_sem <= 0:
        return HttpResponse(
            "Transcript is not available because semesters are not defined for this program.",
            status=400,
        )

    if not _enrollment_is_completed(enrollment, max_sem):
        return HttpResponse(
            "Transcript is not available because all semester results are not completed yet.",
            status=403,
        )

    # Pick ONE SemesterResult per semester: latest batch by created_at (repeat/improved supported).
    qs = (
        SemesterResult.objects.filter(
            enrollment=enrollment,
            batch__program_id=enrollment.program_id,
            batch__session_id=enrollment.session_id,
            batch__semester_number__lte=max_sem,
        )
        .select_related("batch")
        .order_by("batch__semester_number", "-batch__created_at")
    )

    picked = {}
    for sr in qs:
        sem = int(sr.batch.semester_number)
        if sem not in picked:
            picked[sem] = sr

    semesters = []
    picked_batches = []
    cumulative_ch = Decimal("0")
    for sem_no in sorted(picked.keys()):
        sr = picked[sem_no]
        picked_batches.append(sr.batch_id)

        ordered_pcs = list(_course_columns_for_batch(sr.batch))
        ordered_course_ids = [pc.course_id for pc in ordered_pcs]

        cr_qs = (
            CourseResult.objects.filter(batch=sr.batch, enrollment=enrollment)
            .select_related("course")
            .order_by("id")
        )
        cr_map = {cr.course_id: cr for cr in cr_qs}

        course_rows = []
        sem_ch_total = Decimal("0")
        for course_id in ordered_course_ids:
            cr = cr_map.get(course_id)
            if not cr:
                continue
            ch = cr.course.credit_hours
            sem_ch_total += Decimal(str(ch))
            gp_total = (cr.grade_point or 0) * ch
            course_rows.append(
                {
                    "code": cr.course.code,
                    "title": cr.course.title,
                    "credit_hours": ch,
                    "marks_pct": cr.percentage,
                    "grade": cr.letter_grade,
                    "ng": cr.grade_point,
                    "gp_total": gp_total,
                    "marks_obtained": cr.marks_obtained,
                    "max_marks": cr.max_marks,
                }
            )

        cumulative_ch += sem_ch_total

        semesters.append(
            {
                "semester_no": sem_no,
                "batch": sr.batch,
                "semester_result": sr,
                "course_rows": course_rows[:10],  # print-safe (max 10 subjects/semester)
                "sch": sem_ch_total,
                "cch": cumulative_ch,
            }
        )

    # Overall totals across all picked semester batches (overall % for footer)
    overall_obtained = Decimal("0")
    overall_max = Decimal("0")
    if picked_batches:
        totals = CourseResult.objects.filter(
            enrollment=enrollment,
            batch_id__in=picked_batches,
        ).aggregate(
            obt=models.Sum("marks_obtained"),
            mx=models.Sum("max_marks"),
        )
        overall_obtained = totals.get("obt") or Decimal("0")
        overall_max = totals.get("mx") or Decimal("0")

    overall_percentage = None
    if overall_max and overall_max > 0:
        overall_percentage = (overall_obtained / overall_max) * Decimal("100")
        overall_percentage = overall_percentage.quantize(Decimal("0.01"))

    footer_grade = None
    footer_remarks = None
    if overall_percentage is not None:
        gs = (
            GradeScale.objects.filter(
                min_percentage__lte=overall_percentage,
                max_percentage__gte=overall_percentage,
            )
            .order_by("-min_percentage")
            .first()
        )
        if gs:
            footer_grade = gs.letter_grade
            footer_remarks = gs.remarks

    final_cgpa = semesters[-1]["semester_result"].cgpa if semesters else None
    declaration_date = None
    if semesters:
        declaration_date = semesters[-1]["batch"].notification_date

    layout_mode = "single" if max_sem <= 3 else "double"
    semester_pairs = []
    if layout_mode == "double":
        sem_map = {s["semester_no"]: s for s in semesters}
        i = 1
        while i <= max_sem:
            semester_pairs.append({"left": sem_map.get(i), "right": sem_map.get(i + 1)})
            i += 2

    html = render_to_string(
        "results/transcript.html",
        {
            "enrollment": enrollment,
            "student": enrollment.student,
            "program": enrollment.program,
            "session": enrollment.session,
            "session_display": enrollment.session.display_for_program(enrollment.program),
            "max_sem": max_sem,
            "semesters": semesters,
            "layout_mode": layout_mode,
            "semester_pairs": semester_pairs,
            "final_cgpa": final_cgpa,
            "overall_obtained": overall_obtained,
            "overall_max": overall_max,
            "overall_percentage": overall_percentage,
            "footer_letter_grade": footer_grade,
            "footer_remarks": footer_remarks,
            "declaration_date": declaration_date,
        },
        request=request,
    )

    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Transcript_{enrollment.roll_no}.pdf"'
    return response
