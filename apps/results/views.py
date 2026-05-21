from collections import defaultdict
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect
from django.db.models import IntegerField
from django.db.models.functions import Cast, Substr, Reverse, StrIndex, Length
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.db.models import Value, Case, When, CharField
from django.db import models

from weasyprint import HTML

# Note: We use WeasyPrint for all PDF generation. Avoid adding extra PDF merger deps.

from academics.models import Program, Curriculum, CurriculumCourse
from students.models import Enrollment
from .models import ResultBatch, SemesterResult, CourseResult, GradeScale, ResultNotification, ResultNotificationItem
from .services import find_grade_by_gpa, q2
from dashboards.access import get_accessible_batch_or_none, get_accessible_notification_or_none, get_accessible_enrollment_or_none, is_system_admin, is_dealing_assistant

def _fail_letter_set():
    """Return configured failing letter grades (e.g., {'F'})."""
    s = set(GradeScale.objects.filter(is_fail=True).values_list('letter_grade', flat=True))
    # Safe fallback if grade scales are not configured with is_fail
    s.add('F')
    return {str(x).strip() for x in s if str(x).strip()}


def _display_letter_grade_for_pdf(cr: CourseResult, batch: ResultBatch, fail_letters: set[str]) -> str:
    """
    Display-only letter grade used in DMC/Transcript PDFs.

    Rule requested:
    - If a course was previously failed and is now passed in a REPEAT batch,
      suffix 'F' to the obtained letter grade (e.g., 'B' -> 'BF').
    - This does NOT change stored grades/GPA; it's only a PDF display marker.
    """
    lg = (cr.letter_grade or '').strip()
    if not lg:
        return ''

    exam_code = (getattr(getattr(batch, 'exam_type', None), 'code', '') or '').strip().lower()
    # Only for Repeat batches
    if exam_code != 'repeat':
        return lg
    # Only when current attempt is a PASS
    if lg in fail_letters:
        return lg

    # Confirm there exists an earlier FAILED attempt for the same student+course in the same
    # program+session+semester (any earlier batch).
    previously_failed = (
        CourseResult.objects.filter(
            enrollment_id=cr.enrollment_id,
            course_id=cr.course_id,
            batch__program_id=batch.program_id,
            batch__session_id=batch.session_id,
            batch__semester_number=batch.semester_number,
        )
        .exclude(batch_id=batch.id)
        .filter(letter_grade__in=fail_letters)
        .exists()
    )

    return f"{lg}F" if previously_failed else lg



def _course_columns_for_batch(batch: ResultBatch):
    """Return ordered course rows for the batch, limited to courses that exist in the batch.

    Source of truth (v4): CurriculumCourse (via batch.curriculum).
    """
    batch_course_ids = list(
        CourseResult.objects.filter(batch=batch)
        .values_list("course_id", flat=True)
        .distinct()
    )

    if not getattr(batch, "curriculum_id", None):
        # Should not happen: ResultBatch.save() attaches a curriculum.
        return CurriculumCourse.objects.none()

    return (
        CurriculumCourse.objects.filter(
            curriculum_id=batch.curriculum_id,
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
    """
    Natural sorting for roll numbers with hyphen suffix.

    Works for:
      BD1524-10  -> 10
      25-01      -> 1
      CS-2023-15 -> 15

    If '-' is missing, returns 0 (so it won't crash).
    """
    roll = "enrollment__roll_no"

    dash_from_end = StrIndex(Reverse(roll), Value("-"))
    last_dash_pos = Length(roll) - dash_from_end + 1

    suffix_text = Case(
        # Use a safe condition that Django understands: field contains '-'
        When(enrollment__roll_no__contains="-", then=Substr(roll, last_dash_pos + 1)),
        default=Value("0"),
        output_field=CharField(),
    )

    return Cast(suffix_text, IntegerField())


@login_required
def result_notification_pdf(request, batch_id):
    batch = get_accessible_batch_or_none(request.user, batch_id)
    if not batch:
        messages.error(request, "You do not have permission to access that result batch.")
        return redirect("dashboard")


    fail_letters = _fail_letter_set()
    # -------------------------------------------------
    # 1) Find which courses actually appear in THIS batch
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

    # v4: columns come from CurriculumCourse only.
    program_courses = (
        CurriculumCourse.objects.filter(
            curriculum_id=batch.curriculum_id,
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
            # CH: prefer override on CurriculumCourse, else Course, else legacy ProgramCourse
            ch = getattr(pc, "credit_hours_override", None)
            if ch in ("", None):
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
    #    FIXED: works for BD1524-10 and 25-01
    # -------------------------------------------------
    results_qs = (
        SemesterResult.objects.filter(batch=batch)
        .select_related("enrollment", "enrollment__student")
        .annotate(roll_suffix=_roll_suffix_annotation())
        .order_by("roll_suffix", "enrollment__roll_no")
    )

    # Convert to list for stable splitting/iteration in the PDF template.
    results_list = list(results_qs)

    TAIL_ROWS = 3
    if len(results_list) > TAIL_ROWS:
        main_rows = results_list[:-TAIL_ROWS]
        tail_rows = results_list[-TAIL_ROWS:]
    else:
        main_rows = []
        tail_rows = results_list

    # -------------------------------------------------
    # 3.1) Hold map for RL masking (per student)
    # -------------------------------------------------
    hold_map = {sr.enrollment_id: (sr.hold_status or SemesterResult.HOLD_NONE) for sr in results_list}

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

    show_cgpa = sem_no != 1

    # When RL is used, merge marks area + GPA/CGPA into one cell
    rl_colspan = len(columns) + 1 + (1 if show_cgpa else 0)
    total_colspan = 4 + len(columns) + 1 + (1 if show_cgpa else 0)

    # -------------------------------------------------
    # 6) Result type label for header
    # -------------------------------------------------
    result_type_label = getattr(batch.exam_type, "name", "") or ""

    html = render_to_string(
        "results/result_notification.html",
        {
            "batch": batch,
            "notification": None,
            "results": results_list,
            "main_rows": main_rows,
            "tail_rows": tail_rows,
            "columns": columns,
            "grades_map": grades_map,
            "hold_map": hold_map,
            "rl_colspan": rl_colspan,
            "total_colspan": total_colspan,
            "session_display": session_display,
            "show_cgpa": show_cgpa,
            "result_type_label": result_type_label,
        },
        request=request,
    )

    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Result_Notification_{batch.id}.pdf"'
    return response


@login_required
def result_notification_by_id_pdf(request, notification_id):
    """Print a specific notification (supports initial + clearance notifications)."""

    notification = get_accessible_notification_or_none(request.user, notification_id)
    if not notification:
        messages.error(request, "You do not have permission to access that result notification.")
        return redirect("dashboard")
    batch = notification.batch

    fail_letters = _fail_letter_set()

    # Courses in this batch
    batch_course_ids = list(
        CourseResult.objects.filter(batch=batch)
        .values_list("course_id", flat=True)
        .distinct()
    )

    columns = []

    # v4: columns come from CurriculumCourse only.
    program_courses = (
        CurriculumCourse.objects.filter(
            curriculum_id=batch.curriculum_id,
            semester_number=batch.semester_number,
            course_id__in=batch_course_ids,
        )
        .select_related("course")
        .order_by("id")
    )

    if program_courses.exists():
        for pc in program_courses:
            course = pc.course
            looking = getattr(pc, "credit_hours_override", None)
            ch = looking if looking not in ("", None) else getattr(course, "credit_hours", "")
            if ch in ("", None):
                th = getattr(course, "theory_credit", None)
                pr = getattr(course, "practical_credit", None)
                if th is not None or pr is not None:
                    th = th or 0
                    pr = pr or 0
                    ch = f"{th} ({pr})" if pr else f"{th}"
                else:
                    ch = getattr(pc, "credit_hours", "")

            columns.append({"course_id": pc.course_id, "title": getattr(course, "title", str(course)), "credit_hours": ch})
    else:
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
            columns.append({"course_id": cr.course_id, "title": getattr(course, "title", str(course)), "credit_hours": ch})

    # Student rows limited to this notification
    sr_ids = list(notification.items.values_list("semester_result_id", flat=True))
    # IMPORTANT: The PDF template needs reliable slicing of the last N rows.
    # Django QuerySets do not support negative slicing (e.g. qs[:-6]) reliably,
    # so we convert the queryset to a list here.
    results_qs = (
        SemesterResult.objects.filter(id__in=sr_ids)
        .select_related("enrollment", "enrollment__student")
        .annotate(roll_suffix=_roll_suffix_annotation())
        .order_by("roll_suffix", "enrollment__roll_no")
    )
    results_list = list(results_qs)

    # Split rows so the last N rows can be grouped with the signature block.
    # NOTE: This grouping only affects pagination when there isn't enough space;
    # otherwise the tail stays on the same page.
    TAIL_ROWS = 3
    if len(results_list) > TAIL_ROWS:
        main_rows = results_list[:-TAIL_ROWS]
        tail_rows = results_list[-TAIL_ROWS:]
    else:
        main_rows = []
        tail_rows = results_list

    # grades_map
    grades_map = defaultdict(dict)
    enrollment_ids = [r.enrollment_id for r in results_list]
    cr_qs = CourseResult.objects.filter(batch=batch, enrollment_id__in=enrollment_ids).select_related("enrollment", "course")
    for cr in cr_qs:
        grades_map[cr.enrollment_id][cr.course_id] = (cr.letter_grade or "")

    # hold_map from snapshot
    hold_map = {}
    for item in notification.items.select_related("semester_result"):
        hold_map[item.semester_result.enrollment_id] = item.hold_status_snapshot or SemesterResult.HOLD_NONE

    session_display = batch.session.display_for_program(batch.program)
    try:
        sem_no = int(batch.semester_number)
    except Exception:
        sem_no = 0
    show_cgpa = sem_no != 1
    rl_colspan = len(columns) + 1 + (1 if show_cgpa else 0)
    total_colspan = 4 + len(columns) + 1 + (1 if show_cgpa else 0)
    result_type_label = getattr(batch.exam_type, "name", "") or ""

    html = render_to_string(
        "results/result_notification.html",
        {
            "batch": batch,
            "notification": notification,
            "results": results_list,
            "main_rows": main_rows,
            "tail_rows": tail_rows,
            "columns": columns,
            "grades_map": grades_map,
            "hold_map": hold_map,
            "rl_colspan": rl_colspan,
            "total_colspan": total_colspan,
            "session_display": session_display,
            "show_cgpa": show_cgpa,
            "result_type_label": result_type_label,
        },
        request=request,
    )

    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Result_Notification_{notification.id}.pdf"'
    return response


@login_required
def dmc_single_pdf(request, batch_id, enrollment_id):
    """Generate a single-student DMC (one DMC per student per semester/batch)."""
    batch = get_accessible_batch_or_none(request.user, batch_id)
    enrollment = get_accessible_enrollment_or_none(request.user, enrollment_id)
    if not batch or not enrollment:
        messages.error(request, "You do not have permission to access that DMC.")
        return redirect("dashboard")
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


    fail_letters = _fail_letter_set()
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
                "grade": _display_letter_grade_for_pdf(cr, batch, fail_letters),
                "ng": cr.grade_point,
                "gp_total": gp_total,
            }
        )

    course_rows = course_rows[:10]

    # Date of Result on DMC should show the FIRST date the result was notified.
    # If the result is later re-notified, that date may be for declaration purposes only.
    first_notification = batch.notifications.order_by("notification_date", "id").first()
    result_date = first_notification.notification_date if first_notification else getattr(batch, "notification_date", None)

    html = render_to_string(
        "results/dmc_batch.html",
        {
            "batch": batch,
            "session_display": batch.session.display_for_program(batch.program),
            "result_date": result_date,
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
    response["Content-Disposition"] = f'inline; filename="DMC_{batch.id}_{enrollment_id}.pdf"'
    return response


@login_required
def dmc_batch_pdf(request, batch_id):
    """Generate a multi-page PDF (one page per student) for a batch."""
    batch = get_accessible_batch_or_none(request.user, batch_id)
    if not batch:
        messages.error(request, "You do not have permission to access that batch.")
        return redirect("dashboard")

    columns = list(_course_columns_for_batch(batch))
    ordered_course_ids = [pc.course_id for pc in columns]


    fail_letters = _fail_letter_set()
    selected_enrollment_ids = []
    raw_enrollments = request.GET.get("enrollments", "").strip()
    if raw_enrollments:
        selected_enrollment_ids = [int(x) for x in raw_enrollments.split(",") if x.strip().isdigit()]

    results = (
        SemesterResult.objects.filter(batch=batch)
        .select_related("enrollment", "enrollment__student")
        .annotate(roll_suffix=_roll_suffix_annotation())
        .order_by("roll_suffix", "enrollment__roll_no")
    )
    if selected_enrollment_ids:
        results = results.filter(enrollment_id__in=selected_enrollment_ids)

    cr_qs = (
        CourseResult.objects.filter(batch=batch)
        .select_related("course")
        .order_by("id")
    )
    cr_map = defaultdict(dict)
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
                    "grade": _display_letter_grade_for_pdf(cr, batch, fail_letters),
                    "ng": cr.grade_point,
                    "gp_total": gp_total,
                }
            )

        course_rows = course_rows[:10]
        dmcs.append(
            {
                "enrollment": sr.enrollment,
                "student": sr.enrollment.student,
                "semester_result": sr,
                "course_rows": course_rows,
            }
        )

    # Date of Result on DMC should show the FIRST date the result was notified.
    first_notification = batch.notifications.order_by("notification_date", "id").first()
    result_date = first_notification.notification_date if first_notification else getattr(batch, "notification_date", None)

    html = render_to_string(
        "results/dmc_batch.html",
        {
            "batch": batch,
            "session_display": batch.session.display_for_program(batch.program),
            "result_date": result_date,
            "dmcs": dmcs,
        },
        request=request,
    )

    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    filename_prefix = "Selected_DMCs" if selected_enrollment_ids else "DMC_Batch"
    response["Content-Disposition"] = f'inline; filename="{filename_prefix}_{batch.id}.pdf"'
    return response


def _program_total_semesters(program_id: int) -> int:
    """Authoritative total semesters for a program (Program.total_semesters)."""
    program = Program.objects.filter(id=program_id).only("total_semesters").first()
    return int(program.total_semesters) if program else 0


def _program_semester_start(program_id: int) -> int:
    """Semester numbering start for a program (Program.semester_start)."""
    program = Program.objects.filter(id=program_id).only("semester_start").first()
    try:
        return int(getattr(program, "semester_start", 1) or 1)
    except Exception:
        return 1


def _semester_span_for_program_session(program_id: int, session_id: int) -> tuple[int, int, int]:
    """Return (semester_start, semester_end, total_semesters) for Program+Session.

    Prefers Curriculum values (session-specific), otherwise falls back to Program.
    Supports programs where semester numbering doesn't start at 1 (e.g. BS 2 Years: 5..8).
    """
    cur = (
        Curriculum.objects.filter(program_id=program_id, session_id=session_id)
        .only("total_semesters", "semester_start")
        .first()
    )

    if cur:
        total = int(cur.total_semesters or 0)
        start = int(getattr(cur, "semester_start", 1) or 1)
    else:
        total = _program_total_semesters(program_id)
        start = _program_semester_start(program_id)

    if total <= 0:
        return (start or 1, 0, 0)

    start = start or 1
    end = start + total - 1
    return (start, end, total)



def _enrollment_is_completed(
    enrollment: Enrollment, sem_start: int, sem_end: int, total_semesters: int
) -> bool:
    """Completed means: at least one SemesterResult exists for every semester in sem_start..sem_end."""
    if total_semesters <= 0 or sem_end <= 0:
        return False

    done = (
        SemesterResult.objects.filter(
            enrollment=enrollment,
            batch__program_id=enrollment.program_id,
            batch__session_id=enrollment.session_id,
            batch__semester_number__gte=sem_start,
            batch__semester_number__lte=sem_end,
        )
        .values_list("batch__semester_number", flat=True)
        .distinct()
    )
    return len(list(done)) >= int(total_semesters)


@login_required
def transcript_pdf(request, enrollment_id: int):
    enrollment = get_accessible_enrollment_or_none(request.user, enrollment_id)
    if not enrollment:
        messages.error(request, "You do not have permission to access that transcript.")
        return redirect("dashboard")
    enrollment = get_object_or_404(
        Enrollment.objects.select_related(
            "student", "program", "session", "department", "curriculum"
        ),
        id=enrollment_id,
    )

    # Use semester span (supports programs where semester numbering doesn't start at 1)
    if getattr(enrollment, "curriculum_id", None) and getattr(enrollment, "curriculum", None):
        total = int(enrollment.curriculum.total_semesters or 0)
        sem_start = int(getattr(enrollment.curriculum, "semester_start", 1) or 1)
        sem_end = (sem_start + total - 1) if total > 0 else 0
    else:
        sem_start, sem_end, total = _semester_span_for_program_session(enrollment.program_id, enrollment.session_id)

    if total <= 0 or sem_end <= 0:
        return HttpResponse(
            "Transcript is not available because the program duration (total semesters) is not configured.",
            status=400,
        )

    if not _enrollment_is_completed(enrollment, sem_start, sem_end, total):
        return HttpResponse(
            "Transcript is not available because all semester results are not completed yet.",
            status=403,
        )

    qs = (
        SemesterResult.objects.filter(
            enrollment=enrollment,
            batch__program_id=enrollment.program_id,
            batch__session_id=enrollment.session_id,
            batch__semester_number__gte=sem_start,
            batch__semester_number__lte=sem_end,
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

    fail_letters = _fail_letter_set()


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
                    "grade": _display_letter_grade_for_pdf(cr, sr.batch, fail_letters),
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
                "course_rows": course_rows[:10],
                "sch": sem_ch_total,
                "cch": cumulative_ch,
            }
        )

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

    final_cgpa = semesters[-1]["semester_result"].cgpa if semesters else None

    # Transcript footer grade/remarks must be based on FINAL CGPA (not overall marks %)
    footer_grade = None
    footer_remarks = None
    if final_cgpa is not None:
        prefer_a_plus_at_4 = None
        if q2(final_cgpa) == Decimal("4.00") and picked_batches:
            prefer_a_plus_at_4 = not (
                CourseResult.objects.filter(
                    enrollment=enrollment,
                    batch_id__in=picked_batches,
                )
                .exclude(letter_grade="A+")
                .exists()
            )

        footer_grade, _, footer_remarks, _ = find_grade_by_gpa(
            final_cgpa,
            prefer_a_plus_at_4=prefer_a_plus_at_4,
        )
    # Transcript should show the FIRST date the final result was notified (not a later re-notification).
    declaration_date = None
    if semesters:
        final_batch = semesters[-1]["batch"]
        first_notification = final_batch.notifications.order_by("notification_date", "id").first()
        declaration_date = first_notification.notification_date if first_notification else getattr(final_batch, "notification_date", None)

    # Always use the uniform two-column transcript layout.
    layout_mode = "double"
    semester_pairs = []
    sem_map = {s["semester_no"]: s for s in semesters}
    i = sem_start
    while i <= sem_end:
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
            "max_sem": sem_end,
            "sem_start": sem_start,
            "total_semesters": total,
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


@login_required
def transcript_batch_pdf(request, batch_id: int):
    batch = get_accessible_batch_or_none(request.user, batch_id)
    if not batch:
        messages.error(request, "You do not have permission to access that transcript batch.")
        return redirect("dashboard")
    batch = get_object_or_404(ResultBatch.objects.select_related("curriculum"), id=batch_id)

    # Use semester span (supports programs where semester numbering doesn't start at 1)
    if getattr(batch, "curriculum_id", None) and getattr(batch, "curriculum", None):
        total = int(batch.curriculum.total_semesters or 0)
        sem_start = int(getattr(batch.curriculum, "semester_start", 1) or 1)
        sem_end = (sem_start + total - 1) if total > 0 else 0
    else:
        sem_start, sem_end, total = _semester_span_for_program_session(batch.program_id, batch.session_id)

    if not total or int(batch.semester_number) != int(sem_end):
        return HttpResponse("Transcripts are available only for the final semester batch.", status=403)

    selected_enrollment_ids = []
    raw_enrollments = (request.GET.get("enrollments") or "").strip()
    if raw_enrollments:
        selected_enrollment_ids = [int(x) for x in raw_enrollments.split(",") if x.strip().isdigit()]

    results = SemesterResult.objects.filter(batch=batch)
    if selected_enrollment_ids:
        results = results.filter(enrollment_id__in=selected_enrollment_ids)

    results = (
        results
        .select_related("enrollment", "enrollment__student")
        .annotate(roll_suffix=_roll_suffix_annotation())
        .order_by("roll_suffix", "enrollment__roll_no")
    )

    items = []
    # Always use the uniform two-column transcript layout.
    layout_mode = "double"
    # Needed for PDF letter grade display (e.g., show 'F' instead of fail letters like 'D')
    fail_letters = _fail_letter_set()

    for sr in results:
        enrollment = sr.enrollment
        if not _enrollment_is_completed(enrollment, sem_start, sem_end, total):
            continue

        qs = (
            SemesterResult.objects.filter(
                enrollment=enrollment,
                batch__program_id=enrollment.program_id,
                batch__session_id=enrollment.session_id,
                batch__semester_number__gte=sem_start,
                batch__semester_number__lte=sem_end,
            )
            .select_related("batch")
            .order_by("batch__semester_number", "-batch__created_at")
        )

        picked = {}
        for sr2 in qs:
            sem = int(sr2.batch.semester_number)
            if sem not in picked:
                picked[sem] = sr2

        semesters = []
        picked_batches = []
        cumulative_ch = Decimal("0")
        for sem_no in sorted(picked.keys()):
            srp = picked[sem_no]
            picked_batches.append(srp.batch_id)

            ordered_pcs = list(_course_columns_for_batch(srp.batch))
            ordered_course_ids = [pc.course_id for pc in ordered_pcs]

            cr_qs = (
                CourseResult.objects.filter(batch=srp.batch, enrollment=enrollment)
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
                        "grade": _display_letter_grade_for_pdf(cr, srp.batch, fail_letters),
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
                    "batch": srp.batch,
                    "semester_result": srp,
                    "course_rows": course_rows[:10],
                    "sch": sem_ch_total,
                    "cch": cumulative_ch,
                }
            )

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

        final_cgpa = semesters[-1]["semester_result"].cgpa if semesters else None

        # Transcript footer grade/remarks must be based on FINAL CGPA (not overall marks %)
        footer_grade = None
        footer_remarks = None
        if final_cgpa is not None:
            prefer_a_plus_at_4 = None
            if q2(final_cgpa) == Decimal("4.00") and picked_batches:
                prefer_a_plus_at_4 = not (
                    CourseResult.objects.filter(
                        enrollment=enrollment,
                        batch_id__in=picked_batches,
                    )
                    .exclude(letter_grade="A+")
                    .exists()
                )

            footer_grade, _, footer_remarks, _ = find_grade_by_gpa(
                final_cgpa,
                prefer_a_plus_at_4=prefer_a_plus_at_4,
            )
        # Transcript should show the FIRST date the final result was notified.
        declaration_date = None
        if semesters:
            final_batch = semesters[-1]["batch"]
            first_notification = final_batch.notifications.order_by("notification_date", "id").first()
            declaration_date = first_notification.notification_date if first_notification else getattr(final_batch, "notification_date", None)

        semester_pairs = []
        sem_map = {s["semester_no"]: s for s in semesters}
        i = sem_start
        while i <= sem_end:
            semester_pairs.append({"left": sem_map.get(i), "right": sem_map.get(i + 1)})
            i += 2

        items.append(
            {
                "enrollment": enrollment,
                "student": enrollment.student,
                "program": enrollment.program,
                "session": enrollment.session,
                "session_display": enrollment.session.display_for_program(enrollment.program),
                "max_sem": sem_end,
                "sem_start": sem_start,
                "total_semesters": total,
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
            }
        )

    if not items:
        return HttpResponse(
            "No eligible transcripts were found for this batch (all-semester completion required).",
            status=400,
        )

    import re

    prefix = None
    suffix = None
    body_parts = []

    for idx, t in enumerate(items):
        html_full = render_to_string(
            "results/transcript.html",
            {
                "enrollment": t["enrollment"],
                "student": t["student"],
                "program": t["program"],
                "session": t["session"],
                "session_display": t["session_display"],
                "max_sem": t["max_sem"],
                "sem_start": t["sem_start"],
                "total_semesters": t["total_semesters"],
                "semesters": t["semesters"],
                "layout_mode": t["layout_mode"],
                "semester_pairs": t["semester_pairs"],
                "final_cgpa": t["final_cgpa"],
                "overall_obtained": t["overall_obtained"],
                "overall_max": t["overall_max"],
                "overall_percentage": t["overall_percentage"],
                "footer_letter_grade": t["footer_letter_grade"],
                "footer_remarks": t["footer_remarks"],
                "declaration_date": t["declaration_date"],
            },
            request=request,
        )

        if prefix is None:
            m = re.search(r"\A(.*?<body[^>]*>)", html_full, flags=re.S | re.I)
            prefix = m.group(1) if m else "<!doctype html><html><head><meta charset='utf-8'></head><body>"
            m2 = re.search(r"(</body>\s*</html>\s*)\Z", html_full, flags=re.S | re.I)
            suffix = m2.group(1) if m2 else "</body></html>"

        mb = re.search(r"<body[^>]*>(.*)</body>", html_full, flags=re.S | re.I)
        body_inner = mb.group(1) if mb else html_full
        body_parts.append(body_inner)

        if idx != len(items) - 1:
            body_parts.append('<div style="page-break-after: always;"></div>')

    html = (prefix or "") + "".join(body_parts) + (suffix or "")

    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    filename_prefix = "Selected_Transcripts" if selected_enrollment_ids else "Transcripts_Batch"
    response["Content-Disposition"] = f'inline; filename="{filename_prefix}_{batch.id}.pdf"'
    return response