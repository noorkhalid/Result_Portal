from django.contrib import admin
from .models import Student, Enrollment


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "father_name", "registration_no", "is_active")
    search_fields = ("name", "registration_no")
    list_filter = ("is_active",)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "program", "session", "roll_no", "is_active")
    list_filter = ("program", "session", "is_active")
    search_fields = ("roll_no", "student__name", "student__registration_no")
