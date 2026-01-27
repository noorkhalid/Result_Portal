from django.db import models

from academics.models import Department, Program, Session, get_default_department


class Student(models.Model):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="students")

    name = models.CharField(max_length=200)
    father_name = models.CharField(max_length=200)
    registration_no = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.department_id:
            self.department = get_default_department()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.registration_no})"


class Enrollment(models.Model):
    """
    A student enrolled in a Program under a Session (start year).
    Roll number can vary by program/session.
    """

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="enrollments")

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    program = models.ForeignKey(Program, on_delete=models.PROTECT)
    session = models.ForeignKey(Session, on_delete=models.PROTECT)
    roll_no = models.CharField(max_length=50)

    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("program", "session", "roll_no")
        ordering = ["program", "roll_no"]

    def save(self, *args, **kwargs):
        if not self.department_id:
            # Keep in sync with student/program department
            if self.student_id and getattr(self.student, "department_id", None):
                self.department_id = self.student.department_id
            elif self.program_id and getattr(self.program, "department_id", None):
                self.department_id = self.program.department_id
            else:
                self.department = get_default_department()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.program.name} | {self.session.start_year} | {self.roll_no}"
