from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from .models import Department, Program, get_default_department
from students.models import Student  # required for delete protection


# ==================================================
# ACCESS CONTROL
# ==================================================
def is_admin(user):
    return user.is_staff


# ==================================================
# PROGRAMS — LIST
# ==================================================
@login_required
@user_passes_test(is_admin)
def admin_program_list(request):
    department_id = (request.GET.get("department") or "").strip()

    programs = Program.objects.select_related("department").all().order_by("name")
    if department_id:
        programs = programs.filter(department_id=department_id)

    departments = Department.objects.all().order_by("name")

    return render(
        request,
        "dashboards/programs/list.html",
        {
            "programs": programs,
            "departments": departments,
            "department_id": department_id,
        },
    )



# ==================================================
# PROGRAMS — CREATE
# ==================================================
@login_required
@user_passes_test(is_admin)
def admin_program_create(request):
    if request.method == "POST":
        dept_id = request.POST.get("department")
        department = Department.objects.filter(id=dept_id).first() or get_default_department()
        Program.objects.create(
            department=department,
            name=request.POST.get("name"),
            total_semesters=request.POST.get("total_semesters"),
            is_active=True if request.POST.get("is_active") else False,
        )

        messages.success(request, "Program created successfully.")
        return redirect("admin_program_list")

    dept = get_default_department()
    return render(
        request,
        "dashboards/programs/form.html",
        {"departments": Department.objects.all().order_by("name"), "active_department": dept},
    )


# ==================================================
# PROGRAMS — UPDATE
# ==================================================
@login_required
@user_passes_test(is_admin)
def admin_program_update(request, pk):
    program = get_object_or_404(Program, pk=pk)

    if request.method == "POST":
        dept_id = request.POST.get("department")
        department = Department.objects.filter(id=dept_id).first()
        if department:
            program.department = department
        program.name = request.POST.get("name")
        program.total_semesters = request.POST.get("total_semesters")
        program.is_active = True if request.POST.get("is_active") else False
        program.save()

        messages.success(request, "Program updated successfully.")
        return redirect("admin_program_list")

    dept = get_default_department()
    return render(
        request,
        "dashboards/programs/form.html",
        {
            "program": program,
            "departments": Department.objects.all().order_by("name"),
            "active_department": dept,
        },
    )

# # ==================================================
# PROGRAMS — DELETE (SAFE, BUSINESS RULE)
# ==================================================
@login_required
@user_passes_test(is_admin)
def admin_program_delete(request, pk):
    program = get_object_or_404(Program, pk=pk)

    # 🔒 Business rule:
    # Do NOT allow delete if program has enrollments
    if program.enrollment_set.exists():
        return render(
            request,
            "dashboards/programs/confirm_delete.html",
            {
                "program": program,
                "delete_blocked": True,
            },
        )

    if request.method == "POST":
        program.delete()
        return redirect("admin_program_list")

    return render(
        request,
        "dashboards/programs/confirm_delete.html",
        {
            "program": program,
            "delete_blocked": False,
        },
    )

