from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError

from students.models import Student
from academics.models import Department, Program, Session
from django.db.models import Q
from dashboards.decorators import group_required
from dashboards.forms import StudentForm


@group_required("System Admin")
def student_list(request):
    q = (request.GET.get("q") or "").strip()

    department_id = (request.GET.get("department") or "").strip()
    program_id = (request.GET.get("program") or "").strip()
    session_id = (request.GET.get("session") or "").strip()

    students = Student.objects.all().order_by("name")

    if department_id:
        students = students.filter(department_id=department_id)

    # Program/Session filters work through enrollments
    if program_id:
        students = students.filter(enrollments__program_id=program_id)
    if session_id:
        students = students.filter(enrollments__session_id=session_id)

    if q:
        students = students.filter(Q(registration_no__icontains=q) | Q(name__icontains=q))

    students = students.distinct()

    departments = Department.objects.all().order_by("name")
    programs = Program.objects.all().order_by("name")
    sessions = Session.objects.all().order_by("-start_year")

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


@group_required("System Admin")
def student_create(request):
    if request.method == "POST":
        form = StudentForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Student created successfully.")
                return redirect("admin_student_list")
            except IntegrityError:
                messages.error(request, "Registration number must be unique.")
    else:
        form = StudentForm()

    return render(
        request,
        "dashboards/students/form.html",
        {"form": form, "title": "Add Student"},
    )


@group_required("System Admin")
def student_update(request, pk):
    student = get_object_or_404(Student, pk=pk)

    if request.method == "POST":
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Student updated successfully.")
                return redirect("admin_student_list")
            except IntegrityError:
                messages.error(request, "Registration number must be unique.")
    else:
        form = StudentForm(instance=student)

    return render(
        request,
        "dashboards/students/form.html",
        {"form": form, "title": "Edit Student", "student": student},
    )


@group_required("System Admin")
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)

    delete_blocked = student.enrollments.exists()  # related_name="enrollments"

    if request.method == "POST":
        if delete_blocked:
            messages.error(request, "Cannot delete: student has enrollments.")
            return redirect("admin_student_list")

        student.delete()
        messages.success(request, "Student deleted successfully.")
        return redirect("admin_student_list")

    return render(
        request,
        "dashboards/students/confirm_delete.html",
        {"student": student, "delete_blocked": delete_blocked},
    )
