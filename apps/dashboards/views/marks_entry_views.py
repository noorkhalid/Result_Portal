from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render

from dashboards.decorators import group_required
from academics.models import CurriculumCourse
from results.models import CourseResult, ResultBatch
from results.services import recompute_batch
from students.models import Enrollment


@group_required("System Admin", "Data Entry")
def batch_marks_select_course(request, pk: int):
    """Pick a course for manual marks entry within a ResultBatch."""

    batch = get_object_or_404(ResultBatch, pk=pk)

    courses = (
        CurriculumCourse.objects.filter(
            curriculum=batch.curriculum,
            semester_number=batch.semester_number,
        )
        .select_related("course")
        .order_by("course__code")
    )

    if request.method == "POST":
        course_id = (request.POST.get("course_id") or "").strip()
        if not course_id:
            messages.error(request, "Please select a course.")
            return redirect("admin_batch_marks_select_course", pk=batch.id)
        return redirect("admin_batch_marks_entry", pk=batch.id, course_id=int(course_id))

    return render(
        request,
        "dashboards/result_batches/marks_select_course.html",
        {
            "batch": batch,
            "courses": courses,
        },
    )


@group_required("System Admin", "Data Entry")
def batch_marks_entry(request, pk: int, course_id: int):
    """Enter / edit marks for one course in a batch (all students)."""

    batch = get_object_or_404(ResultBatch, pk=pk)

    if batch.is_locked:
        messages.error(request, "This batch is locked. Unlock it before editing marks.")
        return redirect("admin_batch_detail", pk=batch.id)

    course_row = get_object_or_404(
        CurriculumCourse,
        curriculum=batch.curriculum,
        semester_number=batch.semester_number,
        course_id=course_id,
    )
    course = course_row.course

    # Ensure CourseResult rows exist for all enrollments in this batch scope.
    enrollments = (
        Enrollment.objects.filter(
            department=batch.department,
            program=batch.program,
            session=batch.session,
        )
        .select_related("student")
        .order_by("roll_no", "student__registration_no")
    )

    existing = {
        (cr.enrollment_id): cr
        for cr in CourseResult.objects.filter(batch=batch, course=course)
    }

    for e in enrollments:
        if e.id not in existing:
            # Component marks default to 0 for manual entry rows.
            CourseResult.objects.create(
                batch=batch,
                enrollment=e,
                course=course,
                sessional_marks=Decimal("0"),
                midterm_marks=Decimal("0"),
                terminal_marks=Decimal("0"),
                marks_obtained=Decimal("0"),
                max_marks=Decimal("100"),
            )

    qs = (
        CourseResult.objects.filter(batch=batch, course=course)
        .select_related("enrollment", "enrollment__student")
        .order_by("enrollment__roll_no", "enrollment__student__registration_no")
    )

    # If this batch had marks imported before component fields existed,
    # those component fields may be NULL. Prefill them for editing:
    # - Any NULL component becomes 0
    # - If *all* components are NULL but marks_obtained exists, treat it as terminal
    for cr in qs:
        changed = False
        s_is_null = cr.sessional_marks is None
        m_is_null = cr.midterm_marks is None
        t_is_null = cr.terminal_marks is None

        if s_is_null:
            cr.sessional_marks = Decimal("0")
            changed = True
        if m_is_null:
            cr.midterm_marks = Decimal("0")
            changed = True

        if t_is_null:
            # Backfill terminal from total only when ALL components were NULL
            if s_is_null and m_is_null and cr.marks_obtained is not None:
                cr.terminal_marks = cr.marks_obtained
            else:
                cr.terminal_marks = Decimal("0")
            changed = True

        if cr.max_marks is None:
            cr.max_marks = Decimal("100")
            changed = True

        if changed:
            cr.save(update_fields=["sessional_marks", "midterm_marks", "terminal_marks", "max_marks"])

    class CRFormMeta:
        model = CourseResult
        fields = ["sessional_marks", "midterm_marks", "terminal_marks", "max_marks"]

    CRFormSet = modelformset_factory(
        CourseResult,
        fields=CRFormMeta.fields,
        extra=0,
        can_delete=False,
    )

    # Bootstrap widgets
    for fname in CRFormMeta.fields:
        try:
            CRFormSet.form.base_fields[fname].widget.attrs.update(
                {"class": "form-control form-control-sm"}
            )
        except Exception:
            pass

    if request.method == "POST":
        formset = CRFormSet(request.POST, queryset=qs)
        recompute = request.POST.get("recompute") == "on"

        if formset.is_valid():
            formset.save()
            if recompute:
                recompute_batch(batch)
            messages.success(request, "Marks saved successfully.")
            return redirect("admin_batch_marks_entry", pk=batch.id, course_id=course.id)

        messages.error(request, "Please correct the errors below.")
    else:
        formset = CRFormSet(queryset=qs)
        recompute = True

    return render(
        request,
        "dashboards/result_batches/marks_entry.html",
        {
            "batch": batch,
            "course": course,
            "formset": formset,
            "recompute": recompute,
        },
    )
