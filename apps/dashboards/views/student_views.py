from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError
from django.db.models import Q

from students.models import Student
from academics.models import Department, Program, Session
from dashboards.decorators import group_required
from dashboards.forms import StudentForm
from dashboards.access import assigned_departments_qs, is_dealing_assistant


def _assistant_only(user) -> bool:
    return is_dealing_assistant(user) and not (user.is_superuser or user.groups.filter(name="System Admin").exists())


@group_required("System Admin", "Dealing Assistant")
def student_list(request):
    q = (request.GET.get("q") or "").strip()
    department_id = (request.GET.get("department") or "").strip()
    program_id = (request.GET.get("program") or "").strip()
    session_id = (request.GET.get("session") or "").strip()

    students = Student.objects.all().order_by("name")
    assistant_only = _assistant_only(request.user)
    departments = assigned_departments_qs(request.user) if assistant_only else Department.objects.all().order_by("name")

    if department_id:
        students = students.filter(department_id=department_id)
    elif assistant_only:
        students = students.filter(department__assigned_assistant=request.user)

    if program_id:
        students = students.filter(enrollments__program_id=program_id)
    if session_id:
        students = students.filter(enrollments__session_id=session_id)
    if q:
        students = students.filter(Q(registration_no__icontains=q) | Q(name__icontains=q))
    students = students.distinct()

    programs = Program.objects.all().order_by("name")
    if department_id:
        programs = programs.filter(offerings__department_id=department_id, offerings__is_active=True).distinct()
    elif assistant_only:
        programs = programs.filter(offerings__department__assigned_assistant=request.user, offerings__is_active=True).distinct()

    invalid_program = False
    if program_id and not programs.filter(id=program_id).exists():
        invalid_program = True
        program_id = ""
        session_id = ""

    if invalid_program:
        students = Student.objects.all().order_by("name")
        if department_id:
            students = students.filter(department_id=department_id)
        elif assistant_only:
            students = students.filter(department__assigned_assistant=request.user)
        if q:
            students = students.filter(Q(registration_no__icontains=q) | Q(name__icontains=q))
        students = students.distinct()

    enroll_base = Student.objects.all()
    if assistant_only:
        enroll_base = enroll_base.filter(department__assigned_assistant=request.user)
    if department_id:
        enroll_base = enroll_base.filter(department_id=department_id)
    if program_id:
        enroll_base = enroll_base.filter(enrollments__program_id=program_id)
    sessions = Session.objects.filter(
        id__in=enroll_base.values_list("enrollments__session_id", flat=True).distinct()
    ).order_by("-start_year")

    if session_id and not sessions.filter(id=session_id).exists():
        session_id = ""

    return render(
        request,
        "dashboards/students/list.html",
        {
            "students": students,
            "q": q,
            "departments": departments,
            "programs": programs,
            "sessions": sessions,
            "department_id": department_id,
            "program_id": program_id,
            "session_id": session_id,
        },
    )


@group_required("System Admin", "Dealing Assistant")
def student_create(request):
    if request.method == "POST":
        form = StudentForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Student created successfully.")
                return redirect("admin_student_list")
            except IntegrityError:
                messages.error(request, "Registration number must be unique.")
    else:
        form = StudentForm(user=request.user)

    return render(request, "dashboards/students/form.html", {"form": form, "title": "Add Student"})


@group_required("System Admin", "Dealing Assistant")
def student_update(request, pk):
    qs = Student.objects.all()
    if _assistant_only(request.user):
        qs = qs.filter(department__assigned_assistant=request.user)
    student = get_object_or_404(qs, pk=pk)

    if request.method == "POST":
        form = StudentForm(request.POST, instance=student, user=request.user)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Student updated successfully.")
                return redirect("admin_student_list")
            except IntegrityError:
                messages.error(request, "Registration number must be unique.")
    else:
        form = StudentForm(instance=student, user=request.user)

    return render(request, "dashboards/students/form.html", {"form": form, "title": "Edit Student", "student": student})


@group_required("System Admin")
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    delete_blocked = student.enrollments.exists()

    if request.method == "POST":
        if delete_blocked:
            messages.error(request, "Cannot delete: student has enrollments.")
            return redirect("admin_student_list")
        student.delete()
        messages.success(request, "Student deleted successfully.")
        return redirect("admin_student_list")

    return render(request, "dashboards/students/confirm_delete.html", {"student": student, "delete_blocked": delete_blocked})
