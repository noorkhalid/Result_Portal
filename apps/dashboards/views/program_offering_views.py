from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator

from academics.models import Department, Program, ProgramOffering
from dashboards.decorators import group_required
from dashboards.access import assigned_departments_qs, is_dealing_assistant
from dashboards.forms import ProgramOfferingForm


@group_required("System Admin", "Dealing Assistant")
def program_offering_list(request):
    qs = ProgramOffering.objects.select_related("department", "program").all()
    if is_dealing_assistant(request.user) and not (request.user.is_superuser or request.user.groups.filter(name="System Admin").exists()):
        qs = qs.filter(department__assigned_assistant=request.user)

    department_id = (request.GET.get("department") or "").strip()
    program_id = (request.GET.get("program") or "").strip()

    if department_id:
        qs = qs.filter(department_id=department_id)
    if program_id:
        qs = qs.filter(program_id=program_id)

    qs = qs.order_by("department__name", "program__name")

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    params = request.GET.copy()
    params.pop("page", None)
    qs_params = params.urlencode()

    departments = assigned_departments_qs(request.user) if is_dealing_assistant(request.user) and not (request.user.is_superuser or request.user.groups.filter(name="System Admin").exists()) else Department.objects.all().order_by("name")

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
            "items": page_obj.object_list,
            "page_obj": page_obj,
            "qs_params": qs_params,
            "departments": departments,
            "programs": programs,
            "department_id": department_id,
            "program_id": program_id,
        },
    )


@group_required("System Admin", "Dealing Assistant")
def program_offering_create(request):
    if request.method == "POST":
        form = ProgramOfferingForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Program offering created.")
                return redirect("admin_program_offering_list")
            except IntegrityError:
                messages.error(request, "This offering already exists.")
    else:
        form = ProgramOfferingForm(user=request.user)

    return render(
        request,
        "dashboards/program_offerings/form.html",
        {"form": form, "title": "Add Program Offering"},
    )


@group_required("System Admin", "Dealing Assistant")
def program_offering_update(request, pk):
    qs = ProgramOffering.objects.all()
    if is_dealing_assistant(request.user) and not (request.user.is_superuser or request.user.groups.filter(name="System Admin").exists()):
        qs = qs.filter(department__assigned_assistant=request.user)
    item = get_object_or_404(qs, pk=pk)

    if request.method == "POST":
        form = ProgramOfferingForm(request.POST, instance=item, user=request.user)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Program offering updated.")
                return redirect("admin_program_offering_list")
            except IntegrityError:
                messages.error(request, "This offering already exists.")
    else:
        form = ProgramOfferingForm(instance=item, user=request.user)

    return render(
        request,
        "dashboards/program_offerings/form.html",
        {"form": form, "title": "Edit Program Offering", "item": item},
    )


@group_required("System Admin")
def program_offering_delete(request, pk):
    qs = ProgramOffering.objects.all()
    if is_dealing_assistant(request.user) and not (request.user.is_superuser or request.user.groups.filter(name="System Admin").exists()):
        qs = qs.filter(department__assigned_assistant=request.user)
    item = get_object_or_404(qs, pk=pk)

    if request.method == "POST":
        item.delete()
        messages.success(request, "Offering deleted.")
        return redirect("admin_program_offering_list")

    return render(
        request,
        "dashboards/program_offerings/confirm_delete.html",
        {"item": item},
    )
