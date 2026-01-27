from django.contrib import admin

from .models import Student, Enrollment


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "father_name", "registration_no", "department", "is_active")
    search_fields = ("name", "registration_no")
    list_filter = ("department", "is_active")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "program", "session", "roll_no", "department", "is_active")
    list_filter = ("department", "program", "session", "is_active")
    search_fields = ("roll_no", "student__name", "student__registration_no")
