from django.contrib import admin

from .models import Department, Program, Session, Semester, Course, ProgramCourse


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "total_semesters", "is_active")
    list_filter = ("department", "is_active")
    search_fields = ("name",)


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("start_year", "is_active")
    list_filter = ("is_active",)
    search_fields = ("start_year",)


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ("program", "session", "number")
    list_filter = ("program", "session")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "credit_hours")
    search_fields = ("code", "title")
    ordering = ("code",)


@admin.register(ProgramCourse)
class ProgramCourseAdmin(admin.ModelAdmin):
    list_display = ("program", "department", "semester_number", "course")
    list_filter = ("department", "program", "semester_number")
