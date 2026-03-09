from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.core.paginator import Paginator

from .models import Program
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
    qs = Program.objects.all()
    q = (request.GET.get("q") or "").strip()

    if q:
        qs = qs.filter(name__icontains=q)

    qs = qs.order_by("name")

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    params = request.GET.copy()
    params.pop("page", None)
    qs_params = params.urlencode()

    return render(
        request,
        "dashboards/programs/list.html",
        {
            "programs": page_obj.object_list,
            "page_obj": page_obj,
            "qs_params": qs_params,
            "q": q,
        },
    )


# ==================================================
# PROGRAMS — CREATE
# ==================================================
@login_required
@user_passes_test(is_admin)
def admin_program_create(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        total_semesters = request.POST.get("total_semesters")
        semester_start = request.POST.get("semester_start")
        is_active = True if request.POST.get("is_active") else False

        # Friendly validation before hitting DB
        if Program.objects.filter(
            name__iexact=name,
            total_semesters=total_semesters,
        ).exists():
            messages.error(request, "This program already exists with the same duration.")
            return render(request, "dashboards/programs/form.html", {})

        # DB-safe create (race-condition safe)
        try:
            with transaction.atomic():
                Program.objects.create(
                    name=name,
                    total_semesters=total_semesters,
                    semester_start=int(semester_start) if str(semester_start or "").strip() else 1,
                    is_active=is_active,
                )
            messages.success(request, "Program created successfully.")
            return redirect("admin_program_list")
        except IntegrityError:
            messages.error(request, "This program already exists with the same duration.")
            return render(request, "dashboards/programs/form.html", {})

    return render(
        request,
        "dashboards/programs/form.html",
        {},
    )



# ==================================================
# PROGRAMS — UPDATE
# ==================================================
@login_required
@user_passes_test(is_admin)
def admin_program_update(request, pk):
    program = get_object_or_404(Program, pk=pk)

    if request.method == "POST":
        program.name = request.POST.get("name")
        program.total_semesters = request.POST.get("total_semesters")
        semester_start = request.POST.get("semester_start")
        try:
            program.semester_start = int(semester_start) if str(semester_start or "").strip() else 1
        except Exception:
            program.semester_start = 1
        program.is_active = True if request.POST.get("is_active") else False
        program.save()

        messages.success(request, "Program updated successfully.")
        return redirect("admin_program_list")

    return render(
        request,
        "dashboards/programs/form.html",
        {
            "program": program,
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

