from __future__ import annotations

from django.contrib import messages

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from academics.models import Department
from dashboards.decorators import group_required
from dashboards.context_processors import get_active_department


@group_required("System Admin")
def set_active_department(request):
    """Set active department in session and redirect back."""
    next_url = request.GET.get("next") or reverse("dash_system_admin")
    dept_id = request.GET.get("department")

    if dept_id:
        dept = Department.objects.filter(id=dept_id).first()
        if dept:
            request.session["active_department_id"] = dept.id
    else:
        # if not provided, fall back to default
        dept = get_active_department(request)
        request.session["active_department_id"] = dept.id

    return redirect(next_url)


@group_required("System Admin")
def department_list(request):
    departments = Department.objects.all().order_by("name")
    return render(request, "dashboards/departments/list.html", {"departments": departments})


@group_required("System Admin")
def department_create(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, "Department name is required.")
        else:
            Department.objects.get_or_create(name=name)
            messages.success(request, "Department created successfully.")
            return redirect("admin_department_list")

    return render(request, "dashboards/departments/form.html", {"title": "Add Department"})


@group_required("System Admin")
def department_update(request, pk):
    dept = get_object_or_404(Department, pk=pk)

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, "Department name is required.")
        else:
            dept.name = name
            dept.save()
            messages.success(request, "Department updated successfully.")
            return redirect("admin_department_list")

    return render(
        request,
        "dashboards/departments/form.html",
        {"title": "Edit Department", "dept": dept},
    )


@group_required("System Admin")
def department_delete(request, pk):
    dept = get_object_or_404(Department, pk=pk)

    # Prevent deleting a department if it has attached data
    delete_blocked = (
        dept.programs.exists() or dept.program_courses.exists() or dept.students.exists() or dept.enrollments.exists()
    )

    if request.method == "POST":
        if delete_blocked:
            messages.error(request, "Cannot delete: department has linked data.")
            return redirect("admin_department_list")

        dept.delete()
        messages.success(request, "Department deleted successfully.")
        return redirect("admin_department_list")

    return render(
        request,
        "dashboards/departments/confirm_delete.html",
        {"dept": dept, "delete_blocked": delete_blocked},
    )
