from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError

from dashboards.decorators import group_required
from dashboards.forms import ResultBatchForm
from results.models import ResultBatch
from academics.models import Program, Session, Semester


@group_required("System Admin")
def batch_list(request):
    program_id = (request.GET.get("program") or "").strip()
    session_id = (request.GET.get("session") or "").strip()
    semester_no = (request.GET.get("semester") or "").strip()

    base = ResultBatch.objects.select_related("program", "session").all()
    batches = base.order_by("-created_at")

    if program_id:
        batches = batches.filter(program_id=program_id)
    if session_id:
        batches = batches.filter(session_id=session_id)
    if semester_no:
        batches = batches.filter(semester_number=semester_no)

    programs = Program.objects.all().order_by("name")

    # Dependent filter options (narrow based on selected values)
    base_for_sessions = base
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
        if program_id:
            batches = batches.filter(program_id=program_id)

    base_for_semesters = base_for_sessions
    if session_id:
        base_for_semesters = base_for_semesters.filter(session_id=session_id)

    # semester numbers should narrow based on program (+ session)
    semester_numbers = (
        base_for_semesters.values_list("semester_number", flat=True).distinct().order_by("semester_number")
    )

    return render(
        request,
        "dashboards/result_batches/list.html",
        {
            "batches": batches,
            "programs": programs,
            "sessions": sessions,
            "semester_numbers": semester_numbers,
            "program_id": program_id,
            "session_id": session_id,
            "semester_no": semester_no,
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
                messages.error(request, "This batch already exists (program+session+semester+type).")
    else:
        form = ResultBatchForm()

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
                messages.error(request, "This batch already exists (program+session+semester+type).")
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
    return render(
        request,
        "dashboards/result_batches/detail.html",
        {"batch": batch},
    )
