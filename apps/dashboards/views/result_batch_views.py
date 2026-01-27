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

    batches = ResultBatch.objects.select_related("program", "session").all().order_by("-created_at")

    if program_id:
        batches = batches.filter(program_id=program_id)
    if session_id:
        batches = batches.filter(session_id=session_id)
    if semester_no:
        batches = batches.filter(semester_number=semester_no)

    programs = Program.objects.all().order_by("name")
    sessions = Session.objects.all().order_by("-start_year")
    semester_numbers = (
        Semester.objects.values_list("number", flat=True).distinct().order_by("number")
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
