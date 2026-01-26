from __future__ import annotations

import os
from datetime import datetime

import openpyxl
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.db.models import Count
from django.shortcuts import redirect, render

from academics.models import Course, Program, Session
from results.models import CourseResult, ResultBatch
from results.services import recompute_batch
from students.models import Enrollment, Student

from dashboards.decorators import group_required

# ======================================================
# PUBLIC / ENTRY
# ======================================================

def home(request):
    """
    Public entry point.
    If logged in → route to dashboard
    Else → login
    """
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("login")


# ======================================================
# DASHBOARD ROUTER
# ======================================================

@login_required
def dashboard(request):
    """
    Route logged-in users to the correct dashboard
    based on role/group.
    """
    user = request.user

    # System Admin has top priority
@login_required
def dashboard(request):
    """
    Route the logged-in user to the correct dashboard.
    System Admin ALWAYS has priority.
    """
    user = request.user

    # 🔴 Highest priority: System Admin
    if user.is_superuser or user.groups.filter(name="System Admin").exists():
       return redirect("dash_system_admin")

    # Other roles (only checked if NOT System Admin)
    if user.groups.filter(name="Controller").exists():
       return redirect("dash_controller")

    if user.groups.filter(name="Data Entry").exists():
       return redirect("dash_data_entry")

    if user.groups.filter(name="Document Generator").exists():
       return redirect("dash_document_generator")

    if user.groups.filter(name="Result Checker").exists():
       return redirect("dash_result_checker")

    return render(request, "dashboards/no_group.html")


    if user.groups.filter(name="Data Entry").exists():
       return redirect("dash_data_entry")

    if user.groups.filter(name="Document Generator").exists():
       return redirect("dash_document_generator")

    if user.groups.filter(name="Result Checker").exists():
       return redirect("dash_result_checker")

    # No group assigned
    return render(request, "dashboards/no_group.html")


# ======================================================
# ROLE DASHBOARDS
# ======================================================

@group_required("Controller")
def controller_dashboard(request):
    return render(request, "dashboards/controller.html")


@group_required("Data Entry")
def data_entry_dashboard(request):
    """
    Data Entry dashboard with quick stats
    and pending batches.
    """
    unlocked_batches = ResultBatch.objects.filter(is_locked=False).count()
    locked_batches = ResultBatch.objects.filter(is_locked=True).count()

    totals = {
        "students": Student.objects.count(),
        "enrollments": Enrollment.objects.count(),
        "batches": ResultBatch.objects.count(),
        "course_results": CourseResult.objects.count(),
        "unlocked_batches": unlocked_batches,
        "locked_batches": locked_batches,
    }

    todo_batches = (
        ResultBatch.objects.filter(is_locked=False)
        .annotate(cr_count=Count("course_results"))
        .filter(cr_count=0)
        .select_related("program", "session")
        .order_by("-created_at")[:8]
    )

    return render(
        request,
        "dashboards/data_entry.html",
        {
            "totals": totals,
            "todo_batches": todo_batches,
        },
    )


@group_required("Document Generator")
def document_generator_dashboard(request):
    return render(request, "dashboards/document_generator.html")


@group_required("Result Checker")
def result_checker_dashboard(request):
    return render(request, "dashboards/result_checker.html")


@group_required("System Admin")
def system_admin_dashboard(request):
    """
    System Admin dashboard.
    Acts as replacement for Django Admin home.
    """
    return render(request, "dashboards/system_admin.html")


# ======================================================
# DATA ENTRY — EXCEL IMPORT
# ======================================================

def _norm(s: str) -> str:
    """Normalize header strings."""
    return "".join(ch.lower() for ch in str(s).strip() if ch.isalnum())


def _to_float_or_zero(v):
    if v is None or str(v).strip() == "":
        return 0.0
    return float(v)


@group_required("Data Entry")
@transaction.atomic
def data_entry_import_marks(request):
    """
    Upload Excel (.xlsx) file and import marks.
    Logic mirrors results import command.
    """
    if request.method != "POST":
        return render(request, "dashboards/data_entry_import.html")

    recompute = request.POST.get("recompute") == "on"
    xlsx = request.FILES.get("file")

    if not xlsx:
        messages.error(request, "Please choose an Excel (.xlsx) file.")
        return redirect("data_entry_import_marks")

    if not xlsx.name.lower().endswith(".xlsx"):
        messages.error(request, "Only .xlsx files are supported.")
        return redirect("data_entry_import_marks")

    # Save upload
    imports_dir = os.path.join(settings.MEDIA_ROOT, "imports")
    os.makedirs(imports_dir, exist_ok=True)

    fs = FileSystemStorage(location=imports_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = fs.save(f"marks_{ts}_{xlsx.name}", xlsx)
    file_path = fs.path(filename)

    created = 0
    updated = 0
    errors: list[str] = []
    touched_batches: dict[tuple[int, int, int, str], ResultBatch] = {}

    try:
        wb = openpyxl.load_workbook(file_path)
        ws = wb.active

        header_raw = [c.value for c in ws[1]]
        header = [_norm(h) for h in header_raw]

        def col(*names):
            for name in names:
                key = _norm(name)
                if key in header:
                    return header.index(key)
            return None

        reg_i = col("registration_no")
        prog_i = col("program")
        sess_i = col("session")
        sem_i = col("semester")
        code_i = col("course_code", "code")
        title_i = col("course_title", "title")
        ses_i = col("sessional_marks")
        mid_i = col("midterm_marks")
        ter_i = col("terminal_marks")
        max_i = col("maxmarks")
        exam_i = col("examtype")

        required = {
            "registration_no": reg_i,
            "program": prog_i,
            "session": sess_i,
            "semester": sem_i,
            "terminal_marks": ter_i,
            "maxmarks": max_i,
        }

        missing = [k for k, v in required.items() if v is None]
        if missing:
            messages.error(request, f"Missing columns: {', '.join(missing)}")
            return redirect("data_entry_import_marks")

        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            try:
                registration_no = str(row[reg_i]).strip()
                program_name = str(row[prog_i]).strip()
                session_year = int(row[sess_i])
                semester_number = int(row[sem_i])

                terminal = row[ter_i]
                max_marks = row[max_i]

                if terminal is None or max_marks is None:
                    errors.append(f"Row {row_num}: missing marks")
                    continue

                program = Program.objects.filter(name__icontains=program_name).first()
                session = Session.objects.filter(start_year=session_year).first()
                student = Student.objects.filter(registration_no=registration_no).first()

                if not all([program, session, student]):
                    errors.append(f"Row {row_num}: invalid program/session/student")
                    continue

                enrollment = Enrollment.objects.filter(
                    student=student, program=program, session=session
                ).first()

                if not enrollment:
                    errors.append(f"Row {row_num}: enrollment not found")
                    continue

                course = None
                if code_i is not None and row[code_i]:
                    course = Course.objects.filter(code=str(row[code_i]).strip()).first()
                if not course and title_i is not None and row[title_i]:
                    course = Course.objects.filter(title=str(row[title_i]).strip()).first()

                if not course:
                    errors.append(f"Row {row_num}: course not found")
                    continue

                examtype = str(row[exam_i]).lower() if exam_i is not None else "regular"
                result_type = "regular" if examtype not in ("repeat", "improved") else examtype

                key = (program.id, session.id, semester_number, result_type)
                batch = touched_batches.get(key)

                if not batch:
                    batch, _ = ResultBatch.objects.get_or_create(
                        program=program,
                        session=session,
                        semester_number=semester_number,
                        result_type=result_type,
                    )
                    touched_batches[key] = batch

                if batch.is_locked:
                    errors.append(f"Row {row_num}: batch locked")
                    continue

                total = (
                    _to_float_or_zero(row[ses_i] if ses_i is not None else 0)
                    + _to_float_or_zero(row[mid_i] if mid_i is not None else 0)
                    + _to_float_or_zero(terminal)
                )

                cr, created_flag = CourseResult.objects.get_or_create(
                    batch=batch,
                    enrollment=enrollment,
                    course=course,
                    defaults={
                        "marks_obtained": total,
                        "max_marks": float(max_marks),
                    },
                )

                if not created_flag:
                    cr.marks_obtained = total
                    cr.max_marks = float(max_marks)
                    cr.save(update_fields=["marks_obtained", "max_marks"])
                    updated += 1
                else:
                    created += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {e}")

        if recompute:
            for batch in touched_batches.values():
                recompute_batch(batch)

    except Exception as e:
        messages.error(request, f"Import failed: {e}")
        return redirect("data_entry_import_marks")

    return render(
        request,
        "dashboards/data_entry_import_result.html",
        {
            "created": created,
            "updated": updated,
            "error_count": len(errors),
            "errors": errors[:200],
            "batches": list(touched_batches.values()),
        },
    )
