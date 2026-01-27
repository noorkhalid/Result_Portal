from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError

from dashboards.decorators import group_required
from dashboards.forms import GradeScaleForm
from results.models import GradeScale


@group_required("System Admin")
def grade_scale_list(request):
    scales = GradeScale.objects.all().order_by("-min_percentage")
    return render(request, "dashboards/grade_scales/list.html", {"scales": scales})


@group_required("System Admin")
def grade_scale_create(request):
    if request.method == "POST":
        form = GradeScaleForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Grade scale created successfully.")
                return redirect("admin_grade_scale_list")
            except IntegrityError:
                messages.error(request, "Could not create grade scale.")
    else:
        form = GradeScaleForm()

    return render(
        request,
        "dashboards/grade_scales/form.html",
        {"form": form, "title": "Add Grade Scale"},
    )


@group_required("System Admin")
def grade_scale_update(request, pk):
    scale = get_object_or_404(GradeScale, pk=pk)

    if request.method == "POST":
        form = GradeScaleForm(request.POST, instance=scale)
        if form.is_valid():
            form.save()
            messages.success(request, "Grade scale updated successfully.")
            return redirect("admin_grade_scale_list")
    else:
        form = GradeScaleForm(instance=scale)

    return render(
        request,
        "dashboards/grade_scales/form.html",
        {"form": form, "title": "Edit Grade Scale", "scale": scale},
    )


@group_required("System Admin")
def grade_scale_delete(request, pk):
    scale = get_object_or_404(GradeScale, pk=pk)

    if request.method == "POST":
        scale.delete()
        messages.success(request, "Grade scale deleted successfully.")
        return redirect("admin_grade_scale_list")

    return render(
        request,
        "dashboards/grade_scales/confirm_delete.html",
        {"scale": scale},
    )
