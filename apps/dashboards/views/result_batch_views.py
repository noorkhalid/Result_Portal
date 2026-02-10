from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError

from dashboards.decorators import group_required
from dashboards.forms import ResultBatchForm
from results.models import ExamType, ResultBatch
from academics.models import Department, Program, Session
from results.services import recompute_batch


@group_required("System Admin")
def batch_list(request):
    department_id = (request.GET.get("department") or "").strip()
    program_id = (request.GET.get("program") or "").strip()
    session_id = (request.GET.get("session") or "").strip()
    semester_no = (request.GET.get("semester") or "").strip()
    exam_type_id = (request.GET.get("exam_type") or "").strip()

    base = ResultBatch.objects.select_related("department", "program", "session").all()
    batches = base.order_by("-created_at")

    if department_id:
        batches = batches.filter(department_id=department_id)

    if program_id:
        batches = batches.filter(program_id=program_id)
    if session_id:
        batches = batches.filter(session_id=session_id)
    if semester_no:
        batches = batches.filter(semester_number=semester_no)
    if exam_type_id:
        batches = batches.filter(exam_type_id=exam_type_id)

    departments = Department.objects.all().order_by("name")
    programs = Program.objects.all().order_by("name")

    if department_id:
        programs = programs.filter(offerings__department_id=department_id, offerings__is_active=True).distinct()

    # Dependent filter options (narrow based on selected values)
    base_for_sessions = base
    if department_id:
        base_for_sessions = base_for_sessions.filter(department_id=department_id)
    if program_id:
        base_for_sessions = base_for_sessions.filter(program_id=program_id)

    # sessions should narrow when program selected
    sessions = Session.objects.filter(
        id__in=base_for_sessions.values_list("session_id", flat=True).distinct()
    ).order_by("-start_year")

    # If selected session is not valid for this program, reset it (and semester)
    if session_id and not sessions.filter(id=session_id).exists():
        session_id = ""
        semester_no = ""
        # also reset batches filter
        batches = base.order_by("-created_at")
        if department_id:
            batches = batches.filter(department_id=department_id)
        if program_id:
            batches = batches.filter(program_id=program_id)

    base_for_semesters = base_for_sessions
    if session_id:
        base_for_semesters = base_for_semesters.filter(session_id=session_id)

    # semester numbers should narrow based on program (+ session)
    semester_numbers = (
        base_for_semesters.values_list("semester_number", flat=True).distinct().order_by("semester_number")
    )

    base_for_exam_types = base_for_semesters
    if semester_no:
        base_for_exam_types = base_for_exam_types.filter(semester_number=semester_no)

    exam_types = ExamType.objects.filter(
        id__in=base_for_exam_types.values_list("exam_type_id", flat=True).distinct()
    ).order_by("sort_order", "name")

    return render(
        request,
        "dashboards/result_batches/list.html",
        {
            "batches": batches,
            "departments": departments,
            "programs": programs,
            "sessions": sessions,
            "semester_numbers": semester_numbers,
            "exam_types": exam_types,
            "department_id": department_id,
            "program_id": program_id,
            "session_id": session_id,
            "semester_no": semester_no,
            "exam_type_id": exam_type_id,
        },
    )


@group_required("System Admin")
def batch_create(request):
    if request.method == "POST":
        form = ResultBatchForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Result batch created successfully.")
                return redirect("admin_batch_list")
            except IntegrityError:
                messages.error(request, "This batch already exists (program+session+semester+exam type).")
    else:
        # Allow preselecting department (and thus narrowing programs) via GET
        initial = {}
        dept_id = (request.GET.get("department") or "").strip()
        if dept_id:
            initial["department"] = dept_id
        form = ResultBatchForm(initial=initial)

    return render(
        request,
        "dashboards/result_batches/form.html",
        {"form": form, "title": "Add Result Batch"},
    )


@group_required("System Admin")
def batch_update(request, pk):
    batch = get_object_or_404(ResultBatch, pk=pk)

    if request.method == "POST":
        form = ResultBatchForm(request.POST, instance=batch)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Result batch updated successfully.")
                return redirect("admin_batch_list")
            except IntegrityError:
                messages.error(request, "This batch already exists (program+session+semester+exam type).")
    else:
        form = ResultBatchForm(instance=batch)

    return render(
        request,
        "dashboards/result_batches/form.html",
        {"form": form, "title": "Edit Result Batch", "batch": batch},
    )


@group_required("System Admin")
def batch_delete(request, pk):
    batch = get_object_or_404(ResultBatch, pk=pk)

    delete_blocked = batch.course_results.exists() or batch.semester_results.exists()

    if request.method == "POST":
        if delete_blocked:
            messages.error(request, "Cannot delete: results exist in this batch.")
            return redirect("admin_batch_list")

        batch.delete()
        messages.success(request, "Result batch deleted successfully.")
        return redirect("admin_batch_list")

    return render(
        request,
        "dashboards/result_batches/confirm_delete.html",
        {"batch": batch, "delete_blocked": delete_blocked},
    )


@group_required("System Admin")
def batch_detail(request, pk):
    batch = get_object_or_404(ResultBatch, pk=pk)

    # "Last semester" for Transcript availability is defined by Program.total_semesters.
    max_sem = int(getattr(batch.program, "total_semesters", 0) or 0)

    is_last_semester = bool(max_sem and int(batch.semester_number) == int(max_sem))
    has_marks = batch.course_results.exists()
    return render(
        request,
        "dashboards/result_batches/detail.html",
        {
            "batch": batch,
            "is_last_semester": is_last_semester,
            "max_sem": max_sem,
            "has_marks": has_marks,
        },
    )


@group_required("System Admin")
def batch_recompute(request, pk):
    """Recompute GPA/CGPA for a result batch.

    This is needed when marks were imported without ticking the "Recompute" option.
    We keep this action POST-only to avoid accidental recomputation by link clicks.
    """
    batch = get_object_or_404(ResultBatch, pk=pk)

    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("admin_batch_detail", pk=batch.pk)

    if not batch.course_results.exists():
        messages.error(request, "Cannot recompute: no marks exist in this batch.")
        return redirect("admin_batch_detail", pk=batch.pk)

    try:
        recompute_batch(batch)
    except Exception as e:
        messages.error(request, f"Recompute failed: {e}")
        return redirect("admin_batch_detail", pk=batch.pk)

    messages.success(request, "GPA / CGPA recomputed successfully for this batch.")
    return redirect("admin_batch_detail", pk=batch.pk)

