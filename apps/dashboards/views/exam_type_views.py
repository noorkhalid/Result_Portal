from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from dashboards.decorators import group_required
from results.models import ExamType


@group_required("System Admin")
def exam_type_list(request):
    exam_types = ExamType.objects.all().order_by("sort_order", "name")
    return render(request, "dashboards/exam_types/list.html", {"exam_types": exam_types})


@group_required("System Admin")
def exam_type_create(request):
    if request.method == "POST":
        code = (request.POST.get("code") or "").strip().lower()
        name = (request.POST.get("name") or "").strip()
        is_active = bool(request.POST.get("is_active"))
        sort_order = request.POST.get("sort_order") or 0

        if not code:
            messages.error(request, "Code is required.")
        elif not name:
            messages.error(request, "Name is required.")
        else:
            try:
                ExamType.objects.create(
                    code=code,
                    name=name,
                    is_active=is_active,
                    sort_order=sort_order,
                )
                messages.success(request, "Exam type created successfully.")
                return redirect("admin_exam_type_list")
            except IntegrityError:
                messages.error(request, "Exam type already exists (code or name).")

    return render(
        request,
        "dashboards/exam_types/form.html",
        {"title": "Add Exam Type"},
    )


@group_required("System Admin")
def exam_type_update(request, pk):
    exam_type = get_object_or_404(ExamType, pk=pk)

    if request.method == "POST":
        code = (request.POST.get("code") or "").strip().lower()
        name = (request.POST.get("name") or "").strip()
        is_active = bool(request.POST.get("is_active"))
        sort_order = request.POST.get("sort_order") or 0

        if not code:
            messages.error(request, "Code is required.")
        elif not name:
            messages.error(request, "Name is required.")
        else:
            try:
                exam_type.code = code
                exam_type.name = name
                exam_type.is_active = is_active
                exam_type.sort_order = sort_order
                exam_type.save()
                messages.success(request, "Exam type updated successfully.")
                return redirect("admin_exam_type_list")
            except IntegrityError:
                messages.error(request, "Exam type already exists (code or name).")

    return render(
        request,
        "dashboards/exam_types/form.html",
        {"title": "Edit Exam Type", "exam_type": exam_type},
    )


@group_required("System Admin")
def exam_type_delete(request, pk):
    exam_type = get_object_or_404(ExamType, pk=pk)

    delete_blocked = exam_type.result_batches.exists()

    if request.method == "POST":
        if delete_blocked:
            messages.error(request, "Cannot delete: this exam type is used in result batches.")
            return redirect("admin_exam_type_list")

        exam_type.delete()
        messages.success(request, "Exam type deleted successfully.")
        return redirect("admin_exam_type_list")

    return render(
        request,
        "dashboards/exam_types/confirm_delete.html",
        {"exam_type": exam_type, "delete_blocked": delete_blocked},
    )
