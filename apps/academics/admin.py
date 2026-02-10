from django.contrib import admin

from .models import (
    Department,
    Program,
    Session,
    Course,
    ProgramCourse,
    ProgramOffering,
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("name", "total_semesters", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(ProgramOffering)
class ProgramOfferingAdmin(admin.ModelAdmin):
    list_display = ("department", "program", "is_active")
    list_filter = ("department", "program", "is_active")
    search_fields = ("department__name", "program__name")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("start_year", "is_active")
    list_filter = ("is_active",)
    search_fields = ("start_year",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "credit_hours")
    search_fields = ("code", "title")
    ordering = ("code",)


@admin.register(ProgramCourse)
class ProgramCourseAdmin(admin.ModelAdmin):
    list_display = ("program", "semester_number", "course")
    list_filter = ("program", "semester_number")
    search_fields = ("program__name", "course__title", "course__code")
