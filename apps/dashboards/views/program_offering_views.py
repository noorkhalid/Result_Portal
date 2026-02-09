from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from academics.models import Department, Program, ProgramOffering
from dashboards.decorators import group_required
from dashboards.forms import ProgramOfferingForm


@group_required("System Admin")
def program_offering_list(request):
    qs = (
        ProgramOffering.objects.select_related("department", "program")
        .all()
        .order_by("department__name", "program__name")
    )

    department_id = (request.GET.get("department") or "").strip()
    program_id = (request.GET.get("program") or "").strip()

    if department_id:
        qs = qs.filter(department_id=department_id)
    if program_id:
        qs = qs.filter(program_id=program_id)

    departments = Department.objects.all().order_by("name")

    # Program dropdown should depend on selected department.
    # In this project, ProgramOffering.program uses related_name="offerings"
    # (see Program model reverse choices list: 'offerings').
    if department_id:
        programs = (
            Program.objects.filter(offerings__department_id=department_id)
            .distinct()
            .order_by("name")
        )
    else:
        programs = Program.objects.all().order_by("name")

    return render(
        request,
        "dashboards/program_offerings/list.html",
        {
            "items": qs,
            "departments": departments,
            "programs": programs,
            "department_id": department_id,
            "program_id": program_id,
        },
    )


@group_required("System Admin")
def program_offering_create(request):
    if request.method == "POST":
        form = ProgramOfferingForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Program offering created.")
                return redirect("admin_program_offering_list")
            except IntegrityError:
                messages.error(request, "This offering already exists.")
    else:
        form = ProgramOfferingForm()

    return render(
        request,
        "dashboards/program_offerings/form.html",
        {"form": form, "title": "Add Program Offering"},
    )


@group_required("System Admin")
def program_offering_update(request, pk):
    item = get_object_or_404(ProgramOffering, pk=pk)

    if request.method == "POST":
        form = ProgramOfferingForm(request.POST, instance=item)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Program offering updated.")
                return redirect("admin_program_offering_list")
            except IntegrityError:
                messages.error(request, "This offering already exists.")
    else:
        form = ProgramOfferingForm(instance=item)

    return render(
        request,
        "dashboards/program_offerings/form.html",
        {"form": form, "title": "Edit Program Offering", "item": item},
    )


@group_required("System Admin")
def program_offering_delete(request, pk):
    item = get_object_or_404(ProgramOffering, pk=pk)

    if request.method == "POST":
        item.delete()
        messages.success(request, "Offering deleted.")
        return redirect("admin_program_offering_list")

    return render(
        request,
        "dashboards/program_offerings/confirm_delete.html",
        {"item": item},
    )
