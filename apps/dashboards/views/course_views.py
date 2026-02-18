from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from academics.models import Course
from academics.forms import CourseForm

from dashboards.decorators import group_required


# ======================================================
# SYSTEM ADMIN — COURSES CRUD
# ======================================================

@group_required("System Admin")
def course_list(request):
    """
    List all courses.
    """
    q = (request.GET.get("q") or "").strip()

    qs = Course.objects.all()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(title__icontains=q))

    qs = qs.order_by("code")

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    params = request.GET.copy()
    params.pop("page", None)
    qs_params = params.urlencode()

    return render(
        request,
        "dashboards/courses/course_list.html",
        {
            "courses": page_obj.object_list,
            "page_obj": page_obj,
            "qs_params": qs_params,
            "q": q,
        },
    )


@group_required("System Admin")
def course_create(request):
    """
    Create a new course.
    """
    if request.method == "POST":
        form = CourseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Course created successfully.")
            return redirect("admin_course_list")
    else:
        form = CourseForm()

    return render(
        request,
        "dashboards/courses/course_form.html",
        {
            "form": form,
            "title": "Add Course",
        },
    )


@group_required("System Admin")
def course_update(request, pk):
    """
    Edit an existing course.
    """
    course = get_object_or_404(Course, pk=pk)

    if request.method == "POST":
        form = CourseForm(request.POST, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, "Course updated successfully.")
            return redirect("admin_course_list")
    else:
        form = CourseForm(instance=course)

    return render(
        request,
        "dashboards/courses/course_form.html",
        {
            "form": form,
            "title": "Edit Course",
            "course": course,
        },
    )


@group_required("System Admin")
def course_delete(request, pk):
    """
    Delete a course (with confirmation).
    """
    course = get_object_or_404(Course, pk=pk)

    if request.method == "POST":
        course.delete()
        messages.success(request, "Course deleted successfully.")
        return redirect("admin_course_list")

    return render(
        request,
        "dashboards/courses/course_confirm_delete.html",
        {"course": course},
    )
